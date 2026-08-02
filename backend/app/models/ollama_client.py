"""Ollama client — local, open-source models (the free path).

Talks to a running Ollama server (default http://localhost:11434) using its
native /api/chat streaming endpoint. Inference cost is $0.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from ..core.config import settings
from .base import ChatMessage, ModelClient, Usage, estimate_tokens


class OllamaClient(ModelClient):
    provider = "ollama"

    def __init__(self, host: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__()
        self.host = (host or settings.ollama_host).rstrip("/")
        self._transport = transport  # injectable for tests (mock upstream)

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        # Ollama's chat API mirrors OpenAI's message shape but streams NDJSON
        # (one JSON object per line) rather than SSE.
        payload = {
            "model": model or settings.ollama_default_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        prompt_tokens = completion_tokens = 0
        emitted = ""

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0), transport=self._transport) as client:
            async with client.stream(
                "POST", f"{self.host}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                # Each line is a JSON object; the content lives at message.content.
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        emitted += chunk
                        yield chunk
                    # The final line has done=true plus token counts.
                    if data.get("done"):
                        prompt_tokens = data.get("prompt_eval_count", 0)
                        completion_tokens = data.get("eval_count", 0)

        # Ollama is local → $0 inference cost. Fall back to a token estimate if
        # the server didn't report counts.
        self.last_usage = Usage(
            prompt_tokens=prompt_tokens or sum(estimate_tokens(m.content) for m in messages),
            completion_tokens=completion_tokens or estimate_tokens(emitted),
            cost_usd=0.0,
        )
