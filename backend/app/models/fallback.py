"""Fallback resolution — local-fail → API fallback (section 5).

When a primary provider errors (e.g. Ollama isn't running, or an API key is
missing/over quota), the router retries once on a backup provider. The default
backup is configured in settings (`mock` out of the box so demos never break).

Fallbacks are *key-aware*: falling back to a hosted provider whose key isn't
configured would just fail a second time, so an unconfigured provider is
skipped in favour of one that can actually serve the request.
"""

from __future__ import annotations

from ..core.config import settings


def provider_is_usable(provider: str) -> bool:
    """Whether a provider has what it needs to serve a request at all.

    Used to vet an explicitly-chosen fallback before routing to it: naming a
    hosted provider you have no key for would otherwise fail the run outright
    instead of degrading to the safe default.
    """
    if provider == "together":
        return bool(settings.together_api_key)
    if provider == "openrouter":
        return bool(settings.openrouter_api_key)
    # `mock` always works; `ollama` needs no key and can only be checked by
    # actually calling it, so both are treated as usable here.
    return True


def _configured_hosted(exclude: str | None = None) -> tuple[str, str] | None:
    """First hosted provider that actually has an API key, if any.

    Together is preferred over OpenRouter only because it's the cheaper
    open-source path; either works. `exclude` skips the provider that just
    failed, so a fallback never retries the same broken thing.
    """
    if exclude != "together" and settings.together_api_key:
        return "together", settings.together_default_model
    if exclude != "openrouter" and settings.openrouter_api_key:
        return "openrouter", settings.openrouter_default_model
    return None


def resolve_fallback(provider: str) -> tuple[str, str]:
    """Pick the backup (provider, model) for a failed primary."""
    # A local model failing (Ollama down, not pulled) is the main case the
    # hybrid design exists for: reach for a hosted provider that's configured.
    if provider == "ollama":
        if hosted := _configured_hosted():
            return hosted
        return settings.fallback_provider, settings.fallback_model

    # A hosted provider failing (quota, outage, bad key) tries the *other*
    # hosted provider when one is configured, else drops to the safe default.
    if provider in ("together", "openrouter"):
        if hosted := _configured_hosted(exclude=provider):
            return hosted
        return settings.fallback_provider, settings.fallback_model

    return settings.fallback_provider, settings.fallback_model
