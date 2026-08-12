"""Model router — maps an agent's (provider, model) choice to a client.

This is the central switchboard from section 3 of the spec. Add a new provider
by writing a client and registering it here. The router also applies the
fallback chain (e.g. local-fail → hosted API) defined in `fallback.py`.
"""

from __future__ import annotations

from typing import AsyncIterator

from ..core.config import settings
from .base import ChatMessage, ModelClient, StreamResult
from .fallback import resolve_fallback
from .mock_client import MockClient
from .ollama_client import OllamaClient
from .openrouter_client import OpenRouterClient
from .together_client import TogetherClient


class ModelRouter:
    """Stateless switchboard: safe to share as a singleton across concurrent runs.

    Usage/model info for a call is written to the caller-supplied `StreamResult`
    (see `stream`), never to the router itself, so agents streaming in parallel
    can never read each other's token counts.
    """

    def __init__(self) -> None:
        # provider name → client class. A new provider is one line here plus a
        # client module. Clients are cheap and stateless apart from `last_usage`,
        # so we build a fresh one per call to keep usage isolated under
        # concurrency (several agents may stream at once).
        self._factories = {
            "mock": MockClient,
            "ollama": OllamaClient,
            "openrouter": OpenRouterClient,
            "together": TogetherClient,
        }

    @property
    def providers(self) -> list[str]:
        return list(self._factories)

    def _client(self, provider: str) -> ModelClient:
        factory = self._factories.get(provider)
        if factory is None:
            raise ValueError(
                f"Unknown model provider '{provider}'. "
                f"Available: {', '.join(self._factories)}"
            )
        return factory()

    def _resolve(self, provider: str, fallback: str | None) -> tuple[str, str]:
        """Pick the backup (provider, model): per-agent override, else global.

        The override is "provider:model"; a bare "model" keeps the current
        provider. An unknown provider falls through to the global chain rather
        than raising, so a typo can't break an otherwise-healthy run.
        """
        if fallback:
            fb_provider, _, fb_model = fallback.partition(":")
            if not fb_model:  # bare model name → same provider
                fb_provider, fb_model = provider, fb_provider
            if fb_provider in self._factories:
                return fb_provider, fb_model
        return resolve_fallback(provider)

    async def stream(
        self,
        provider: str,
        model: str,
        messages: list[ChatMessage],
        *,
        result: StreamResult | None = None,
        fallback: str | None = None,
        tools: list[dict] | None = None,
        allow_fallback: bool = True,
    ) -> AsyncIterator[str]:
        """Stream a chat completion, transparently falling back on failure.

        Yields text chunks. Pass a `StreamResult` to receive the usage and the
        model that actually ran (which may be the fallback) once the stream
        finishes. Because that object is caller-owned, the router keeps no
        per-call state and is safe to share across concurrent agents.

        `fallback` is an optional per-agent override formatted "provider:model";
        when absent the global chain in `fallback.py` applies.
        """
        # --- Primary attempt ---
        emitted = False  # did the caller already receive part of this response?
        primary = self._client(provider)
        try:
            # Only offer tools to clients that implement tool calling — and pass
            # the argument only when there are tools, so simpler clients can keep
            # the two-parameter stream_chat signature.
            kwargs = {"tools": tools} if (tools and primary.supports_tools) else {}
            async for chunk in primary.stream_chat(model, messages, **kwargs):
                emitted = True
                yield chunk
            # Success: hand the client's usage back through the caller's result.
            if result is not None:
                result.usage = primary.last_usage
                result.model = f"{provider}:{model}"
                result.tool_calls = primary.last_tool_calls
            return
        except Exception:  # noqa: BLE001 - any failure should fall back
            # Falling back mid-stream would splice a partial primary response
            # onto a complete fallback one, producing garbled output. Once any
            # text has been emitted the only honest move is to surface the
            # error and let the caller retry the attempt from scratch.
            if emitted or not allow_fallback:
                raise
            fb_provider, fb_model = self._resolve(provider, fallback)
            if fb_provider == provider and fb_model == model:
                raise  # nowhere to fall back to → surface the error

        # --- Fallback path (e.g. Ollama down → mock, or OpenRouter → mock) ---
        backup = self._client(fb_provider)
        fb_kwargs = {"tools": tools} if (tools and backup.supports_tools) else {}
        async for chunk in backup.stream_chat(fb_model, messages, **fb_kwargs):
            yield chunk
        if result is not None:
            result.usage = backup.last_usage
            result.tool_calls = backup.last_tool_calls
            # The "(fallback)" suffix is visible in the run trace so it's obvious
            # the requested model wasn't the one that ran.
            result.model = f"{fb_provider}:{fb_model} (fallback)"


# Module-level singleton — one router shared across the app.
_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
