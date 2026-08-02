"""OpenRouter client — single gateway to many hosted models.

OpenRouter exposes an OpenAI-compatible API, so this one integration covers
Claude, GPT, Gemini, Groq-served Llama, and more. Users pick any model by its
OpenRouter id (e.g. "anthropic/claude-3.5-haiku"); cost is estimated from the
returned token usage.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from ..core.config import settings
from .base import ChatMessage, ModelClient, Usage, estimate_cost, estimate_tokens


class OpenRouterClient(ModelClient):
    provider = "openrouter"

    def __init__(self, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__()
        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url.rstrip("/")
        self._transport = transport  # injectable for tests (mock upstream)

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        # Fail loudly (so the router can fall back) when no key is configured.
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to .env or route this "
                "agent to the 'ollama' or 'mock' provider."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://taskforce.local",  # OpenRouter attribution
            "X-Title": "TaskForce",
        }
        payload = {
            "model": model or settings.openrouter_default_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "usage": {"include": True},  # ask OpenRouter to include token usage
        }
        emitted = ""
        prompt_tokens = completion_tokens = 0

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0), transport=self._transport) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", headers=headers, json=payload
            ) as resp:
                resp.raise_for_status()
                # OpenAI-style Server-Sent Events: lines like "data: {json}".
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue  # skip blank lines / comments
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break  # end-of-stream sentinel
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    # Incremental text lives in choices[0].delta.content.
                    choices = data.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {}).get("content")
                        if delta:
                            emitted += delta
                            yield delta
                    # A trailing event carries the final token usage.
                    if usage := data.get("usage"):
                        prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                        completion_tokens = usage.get("completion_tokens", completion_tokens)

        # Estimate counts if the API didn't send them, then price the call.
        prompt_tokens = prompt_tokens or sum(estimate_tokens(m.content) for m in messages)
        completion_tokens = completion_tokens or estimate_tokens(emitted)
        self.last_usage = Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=estimate_cost(
                model or settings.openrouter_default_model,
                prompt_tokens,
                completion_tokens,
            ),
        )
