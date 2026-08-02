"""Verify the real model clients against mock upstreams over a real HTTP transport.

Uses httpx's ASGITransport so the clients exercise their genuine streaming/parse
paths — proving the Ollama + OpenRouter wiring works without a live server.
"""

import json

import httpx
import pytest

from app.models.base import ChatMessage
from app.models.ollama_client import OllamaClient
from app.models.openrouter_client import OpenRouterClient


async def _drain(receive):
    while True:
        msg = await receive()
        if not msg.get("more_body"):
            break


async def ollama_upstream(scope, receive, send):
    await _drain(receive)
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/x-ndjson")]})
    chunks = [
        {"message": {"content": "Hello "}},
        {"message": {"content": "world"}},
        {"done": True, "prompt_eval_count": 11, "eval_count": 3},
    ]
    for i, c in enumerate(chunks):
        await send({"type": "http.response.body",
                    "body": (json.dumps(c) + "\n").encode(),
                    "more_body": i < len(chunks) - 1})


async def openrouter_upstream(scope, receive, send):
    await _drain(receive)
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"text/event-stream")]})
    events = [
        'data: {"choices":[{"delta":{"content":"Hi "}}]}\n\n',
        'data: {"choices":[{"delta":{"content":"there"}}]}\n\n',
        'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":2}}\n\n',
        "data: [DONE]\n\n",
    ]
    for i, e in enumerate(events):
        await send({"type": "http.response.body", "body": e.encode(),
                    "more_body": i < len(events) - 1})


@pytest.mark.asyncio
async def test_ollama_client_streams_and_reports_free():
    client = OllamaClient(host="http://upstream",
                          transport=httpx.ASGITransport(app=ollama_upstream))
    out = [c async for c in client.stream_chat("llama3.1:8b", [ChatMessage("user", "hi")])]
    assert "".join(out) == "Hello world"
    assert client.last_usage.prompt_tokens == 11
    assert client.last_usage.completion_tokens == 3
    assert client.last_usage.cost_usd == 0.0  # local = free


@pytest.mark.asyncio
async def test_openrouter_client_streams_and_costs():
    client = OpenRouterClient(api_key="test-key",
                              transport=httpx.ASGITransport(app=openrouter_upstream))
    out = [c async for c in client.stream_chat("openai/gpt-4o-mini", [ChatMessage("user", "hi")])]
    assert "".join(out) == "Hi there"
    assert client.last_usage.prompt_tokens == 12
    assert client.last_usage.completion_tokens == 2
    assert client.last_usage.cost_usd > 0  # hosted = billed


@pytest.mark.asyncio
async def test_openrouter_requires_key():
    client = OpenRouterClient(api_key=None)
    with pytest.raises(RuntimeError):
        async for _ in client.stream_chat("openai/gpt-4o-mini", [ChatMessage("user", "hi")]):
            pass
