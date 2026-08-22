"""Access control for a publicly-reachable deployment.

The deployed app is meant to be shareable — anyone with the link can browse
workflows and watch one run live. What they cannot do is **spend your money** or
**change your data**; both require the admin token.

Three layers, because they solve different problems:

  * admin token  — controls WHO can mutate data and use real (billed) models
  * rate limit   — controls HOW FAST any single client can trigger runs
  * spend cap    — controls your MAXIMUM BILL, and is the only one that truly
                   bounds cost (a rate limit still lets 50 visitors × 2 runs
                   through, and per-IP limits are bypassed with a proxy)

Everything here is a **no-op when ADMIN_TOKEN is unset**, so local development
and the test suite behave exactly as they did before gating existed. That
mirrors how WEBHOOK_SECRET already works.
"""

from __future__ import annotations

import hmac
from datetime import datetime, timezone

from fastapi import Header, HTTPException, Request

from ..db.store import store
from .config import settings
from .ratelimit import RateLimiter

# Per-IP limiter for endpoints that can start a run. Built from settings at
# import time; a single shared instance so every entry point shares one budget.
run_limiter = RateLimiter(
    max_events=settings.rate_limit_runs,
    window_seconds=settings.rate_limit_window_seconds,
)


# --- Admin token -----------------------------------------------------------

def gating_enabled() -> bool:
    """True when an ADMIN_TOKEN is configured (i.e. this is a public deploy)."""
    return bool(settings.admin_token)


def is_admin(supplied: str | None) -> bool:
    """Constant-time token check. Always True when gating is disabled."""
    expected = settings.admin_token
    if not expected:
        return True  # no token configured → unrestricted (local dev / tests)
    if not supplied:
        return False
    # compare_digest avoids leaking the token through response-timing.
    return hmac.compare_digest(supplied, expected)


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """FastAPI dependency: 401 unless the caller is an admin.

    Used on every mutating workflow route, so a public visitor can run the demo
    but can't create, edit, or delete anything.
    """
    if not is_admin(x_admin_token):
        raise HTTPException(
            status_code=401,
            detail="This action requires the admin token (send it as X-Admin-Token).",
        )


def admin_from_request(request: Request) -> bool:
    """Read the admin flag off a raw Request (for routes that aren't using the
    dependency, e.g. ones that must stay open but behave differently)."""
    return is_admin(request.headers.get("x-admin-token"))


# --- Client identity -------------------------------------------------------

def client_ip(request_or_ws) -> str:
    """Best-effort client IP, honouring the proxy header.

    Behind Railway/Render the socket peer is the platform's proxy, so the real
    client is the first entry of X-Forwarded-For. That header is client-supplied
    and therefore spoofable — which is exactly why the spend cap, not the rate
    limit, is what actually protects the bill.
    """
    forwarded = request_or_ws.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    peer = getattr(request_or_ws, "client", None)
    return getattr(peer, "host", None) or "unknown"


# --- Spend circuit breaker -------------------------------------------------

def spent_today() -> float:
    """Cumulative cost of every run started so far this UTC day."""
    midnight = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return store.spend_since(midnight.isoformat())


def budget_remaining() -> float | None:
    """Dollars left in today's budget, or None when no limit is configured."""
    limit = settings.daily_cost_limit_usd
    if limit is None:
        return None
    return max(0.0, limit - spent_today())


def enforce_budget() -> None:
    """Raise 429 when today's spend cap is already reached.

    Checked before a run starts rather than mid-run: it can't stop a single
    expensive run from overshooting slightly, but it does stop the NEXT one,
    which is what keeps a runaway loop bounded.
    """
    limit = settings.daily_cost_limit_usd
    if limit is None:
        return
    spent = spent_today()
    if spent >= limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily spend limit reached (${spent:.4f} of ${limit:.2f}). "
                "Runs resume at 00:00 UTC."
            ),
        )


def enforce_rate_limit(request_or_ws) -> None:
    """Raise 429 when this client has triggered too many runs recently."""
    if not run_limiter.allow(client_ip(request_or_ws)):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit reached ({settings.rate_limit_runs} runs per "
                f"{settings.rate_limit_window_seconds // 60} minutes). Try again later."
            ),
        )
