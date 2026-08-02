"""Fallback resolution — local-fail → API fallback (section 5).

When a primary provider errors (e.g. Ollama isn't running, or an API key is
missing/over quota), the router retries once on a backup provider. The default
backup is configured in settings (`mock` out of the box so demos never break).
"""

from __future__ import annotations

from ..core.config import settings

# Per-provider override of where to fall back to. Anything not listed uses the
# global fallback from settings.
_FALLBACK_MAP: dict[str, tuple[str, str]] = {
    "ollama": ("openrouter", settings.openrouter_default_model),
    "openrouter": (settings.fallback_provider, settings.fallback_model),
}


def resolve_fallback(provider: str) -> tuple[str, str]:
    fb_provider, fb_model = _FALLBACK_MAP.get(
        provider, (settings.fallback_provider, settings.fallback_model)
    )
    # If the API-based fallback has no key configured, drop to mock so the run
    # still completes (and the trace records that a fallback occurred).
    if fb_provider == "openrouter" and not settings.openrouter_api_key:
        return settings.fallback_provider, settings.fallback_model
    return fb_provider, fb_model
