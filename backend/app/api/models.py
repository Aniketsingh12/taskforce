"""Available models, providers, and tools — what the UI's pickers read from."""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Header

from ..core.config import settings
from ..core.security import is_admin
from ..models import get_router
from ..models.base import PRICE_TABLE
from ..tools import list_tools

router = APIRouter(prefix="/api", tags=["models"])

# Together's catalog is fetched with YOUR API key, and the Ollama list reflects
# what's installed on YOUR server — both are account/infrastructure detail, so
# neither is served to anonymous visitors (who are forced onto the demo model
# and couldn't select them anyway).
#
# Cached briefly so a page refresh — or someone hammering this endpoint —
# doesn't turn into a burst of authenticated calls against your provider
# account. Listing models is free, but it still consumes rate limit.
_CATALOG_TTL_SECONDS = 300
_together_cache: tuple[float, list[str], bool] | None = None

# Shown when Ollama isn't reachable, so the picker still suggests sensible
# 8GB-friendly models to pull.
_SUGGESTED_LOCAL = [settings.ollama_default_model, "qwen2.5:7b", "phi3.5"]

# Shown when no TOGETHER_API_KEY is set yet, so the picker isn't empty before
# the first key is added. Not authoritative — see _together_models below.
_SUGGESTED_TOGETHER = [settings.together_default_model]


async def _ollama_models() -> tuple[list[str], bool]:
    """Ask the local Ollama server which models are actually pulled.

    Returns (model_names, is_live). Falls back to the suggested list when the
    server isn't running, so the UI never advertises models you don't have
    without saying so.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
            resp.raise_for_status()
            names = [m["name"] for m in resp.json().get("models", []) if m.get("name")]
        if names:
            return sorted(names), True
    except Exception:  # noqa: BLE001 - Ollama not installed/running is normal
        pass
    return _SUGGESTED_LOCAL, False


async def _together_models() -> tuple[list[str], bool]:
    """Ask Together's own API which models are actually available right now.

    Together's catalog changes fast and isn't worth hardcoding — this is the
    authoritative source for "what's the best model available": it's always
    exactly Together's current lineup, not a guess baked into this codebase.
    Falls back to a single suggested id (flagged as not live) when no key is
    configured yet, or the request fails for any reason.
    """
    global _together_cache

    if not settings.together_api_key:
        return _SUGGESTED_TOGETHER, False

    # Serve a recent result rather than re-querying on every page load.
    if _together_cache is not None:
        fetched_at, names, live = _together_cache
        if time.monotonic() - fetched_at < _CATALOG_TTL_SECONDS:
            return names, live

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.together_base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {settings.together_api_key}"},
            )
            resp.raise_for_status()
            body = resp.json()
            # OpenAI-compatible /v1/models: {"object": "list", "data": [...]}.
            # Defensive about the exact shape since it's a third-party API.
            entries = body.get("data") if isinstance(body, dict) else body
            entries = entries or []
            # Keep chat-capable models; drop anything explicitly flagged as
            # embedding/image/moderation/etc. A model with no "type" field at
            # all is kept rather than dropped — better a few extra options
            # than silently hiding real ones over a wrong field-name guess.
            names = [
                e["id"] for e in entries
                if isinstance(e, dict) and e.get("id")
                and e.get("type") in (None, "chat", "language")
            ]
        if names:
            _together_cache = (time.monotonic(), sorted(names), True)
            return sorted(names), True
    except Exception:  # noqa: BLE001 - bad key / network issue / API shape surprise
        pass
    # Cache the failure too, so a bad key or an outage doesn't mean a fresh
    # failing request on every single page load.
    _together_cache = (time.monotonic(), _SUGGESTED_TOGETHER, False)
    return _SUGGESTED_TOGETHER, False


@router.get("/models")
async def available_models(x_admin_token: str | None = Header(default=None)) -> dict:
    """Models grouped by provider, with cost-per-1M-token where known.

    **Admin-scoped.** The Together catalog is queried with your API key and the
    local list reflects what's installed on your server — both are account and
    infrastructure detail, so an anonymous visitor is shown only the demo model
    they're actually allowed to run. Nothing is hidden from you.
    """
    demo_entry = {
        "provider": settings.demo_provider, "model": settings.demo_model,
        "is_local": True, "cost_in": 0.0, "cost_out": 0.0,
    }

    if not is_admin(x_admin_token):
        return {
            "providers": [settings.demo_provider],
            "restricted": True,  # the UI explains why the list is short
            "ollama_live": False,
            "together_live": False,
            "local": [],
            "hosted": [],
            "together": [],
            "demo": [demo_entry],
        }

    local_names, ollama_live = await _ollama_models()
    together_names, together_live = await _together_models()
    return {
        "providers": get_router().providers,
        "restricted": False,
        "ollama_live": ollama_live,  # False → the local list is a suggestion
        "together_live": together_live,  # False → no key set, list is a suggestion
        "local": [
            {"provider": "ollama", "model": name, "is_local": True,
             "cost_in": 0.0, "cost_out": 0.0, "installed": ollama_live}
            for name in local_names
        ],
        "hosted": [
            # Static reference pricing from PRICE_TABLE — public data compiled
            # into the repo, not derived from your account.
            {"provider": "openrouter", "model": m, "is_local": False,
             "cost_in": price[0], "cost_out": price[1]}
            for m, price in PRICE_TABLE.items() if m != "mock-default"
        ],
        "together": [
            # Pricing isn't returned per-model in a stable shape, so cost is
            # left at 0 rather than shown wrong; the trace still records real
            # token counts from the API response.
            {"provider": "together", "model": name, "is_local": False,
             "cost_in": 0.0, "cost_out": 0.0}
            for name in together_names
        ],
        "demo": [demo_entry],
    }


@router.get("/tools")
def available_tools() -> list[dict]:
    return list_tools()
