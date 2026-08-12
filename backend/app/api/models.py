"""Available models, providers, and tools — what the UI's pickers read from."""

from __future__ import annotations

import httpx
from fastapi import APIRouter

from ..core.config import settings
from ..models import get_router
from ..models.base import PRICE_TABLE
from ..tools import list_tools

router = APIRouter(prefix="/api", tags=["models"])

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
    if not settings.together_api_key:
        return _SUGGESTED_TOGETHER, False
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
            return sorted(names), True
    except Exception:  # noqa: BLE001 - bad key / network issue / API shape surprise
        pass
    return _SUGGESTED_TOGETHER, False


@router.get("/models")
async def available_models() -> dict:
    """Models grouped by provider, with cost-per-1M-token where known.

    Local (Ollama) models are free and read live from the Ollama server;
    hosted models show estimated pricing.
    """
    local_names, ollama_live = await _ollama_models()
    together_names, together_live = await _together_models()
    return {
        "providers": get_router().providers,
        "ollama_live": ollama_live,  # False → the local list is a suggestion
        "together_live": together_live,  # False → no key set, list is a suggestion
        "local": [
            {"provider": "ollama", "model": name, "is_local": True,
             "cost_in": 0.0, "cost_out": 0.0, "installed": ollama_live}
            for name in local_names
        ],
        "hosted": [
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
        "demo": [
            {"provider": "mock", "model": "mock-default", "is_local": True, "cost_in": 0.0, "cost_out": 0.0},
        ],
    }


@router.get("/tools")
def available_tools() -> list[dict]:
    return list_tools()
