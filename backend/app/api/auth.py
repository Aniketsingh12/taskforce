"""Access status — lets the UI show the right mode and controls.

Deliberately does NOT verify-or-401: the whole point is that an anonymous
visitor gets a useful answer ("you're in demo mode") rather than a wall.
"""

from __future__ import annotations

from fastapi import APIRouter, Header

from ..core.config import settings
from ..core.security import budget_remaining, gating_enabled, is_admin, spent_today

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status(x_admin_token: str | None = Header(default=None)) -> dict:
    """Who am I, and what am I allowed to do?

    Spend figures are returned only to an admin — a public visitor has no
    business knowing your remaining budget.
    """
    admin = is_admin(x_admin_token)
    body = {
        # True when this deployment gates anything at all (ADMIN_TOKEN is set).
        "gating_enabled": gating_enabled(),
        "admin": admin,
        # True when this caller's runs will be forced onto the demo model.
        "demo_mode": gating_enabled() and not admin,
        "demo_model": f"{settings.demo_provider}:{settings.demo_model}",
        # A wrong/absent token when gating is on — lets the UI show "invalid".
        "token_supplied": bool(x_admin_token),
    }
    if admin:
        body["spent_today"] = round(spent_today(), 6)
        body["daily_limit"] = settings.daily_cost_limit_usd
        remaining = budget_remaining()
        body["budget_remaining"] = None if remaining is None else round(remaining, 6)
    return body
