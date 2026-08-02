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


@router.get("/models")
async def available_models() -> dict:
    """Models grouped by provider, with cost-per-1M-token where known.

    Local (Ollama) models are free and read live from the Ollama server;
    hosted models show estimated pricing.
    """
    local_names, ollama_live = await _ollama_models()
    return {
        "providers": get_router().providers,
        "ollama_live": ollama_live,  # False → the local list is a suggestion
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
        "demo": [
            {"provider": "mock", "model": "mock-default", "is_local": True, "cost_in": 0.0, "cost_out": 0.0},
        ],
    }


@router.get("/tools")
def available_tools() -> list[dict]:
    return list_tools()
