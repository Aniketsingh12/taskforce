"""Model-driven tool calling: the loop, its bounds, and wire-format parsing."""

import asyncio
import json

import httpx
import pytest

from app.db.schema import AgentConfig
from app.models import ChatMessage, ModelRouter, StreamResult
from app.models.base import ModelClient, ToolCall, Usage
from app.models.openrouter_client import OpenRouterClient
from app.orchestration.react import stream_with_tools


def test_loop_emits_tool_call_events_with_arguments():
    """The UI needs to see what the model decided to call, and with what."""
    agent = AgentConfig(role="Researcher", instructions="research", tools=["web_search"])
    events: list[dict] = []
    result = StreamResult()

    async def go():
        chunks = []
        async for c in stream_with_tools(
            router=ModelRouter(), agent=agent,
            messages=[
                ChatMessage("system", "You are a meticulous researcher."),
                ChatMessage("user", "# Workflow goal / input\nquantum widgets"),
            ],
            emit=lambda e: events.append(e), result=result,
        ):
            chunks.append(c)
        return "".join(chunks)

    text = asyncio.run(go())

    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["tool"] == "web_search"
    # The model passed a real query pulled from the goal, not boilerplate.
    assert "quantum widgets" in calls[0]["arguments"]["query"]
    # The tool ran, was recorded, and the final answer followed the tool turn.
    assert result.tools_called == ["web_search"]
    assert "key findings" in text


class AlwaysCallsTools(ModelClient):
    """A model that never stops asking for tools — the runaway case."""

    provider = "greedy"
    supports_tools = True
    turns = 0

    async def stream_chat(self, model, messages, tools=None):
        type(self).turns += 1
        self.last_tool_calls = (
            [ToolCall(id="c", name="web_search", arguments={"query": "again"})]
            if tools else []
        )
        yield "thinking "
        self.last_usage = Usage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0)


def test_max_tool_steps_bounds_a_runaway_loop():
    AlwaysCallsTools.turns = 0
    router = ModelRouter()
    router._factories = {**router._factories, "greedy": AlwaysCallsTools}

    agent = AgentConfig(role="R", instructions="x", tools=["web_search"],
                        model_provider="greedy", model_name="m", max_tool_steps=3)
    result = StreamResult()

    async def go():
        async for _ in stream_with_tools(
            router=router, agent=agent,
            messages=[ChatMessage("user", "go")],
            emit=lambda e: None, result=result,
        ):
            pass

    asyncio.run(go())
    # Exactly max_tool_steps turns, and the final one runs WITHOUT tools so the
    # model is forced to answer rather than loop forever.
    assert AlwaysCallsTools.turns == 3
    assert len(result.tools_called) == 2


def test_usage_accumulates_across_every_turn():
    """Cost/tokens must cover the whole chain, not just the final message."""
    AlwaysCallsTools.turns = 0
    router = ModelRouter()
    router._factories = {**router._factories, "greedy": AlwaysCallsTools}
    agent = AgentConfig(role="R", instructions="x", tools=["web_search"],
                        model_provider="greedy", model_name="m", max_tool_steps=3)
    result = StreamResult()

    async def go():
        async for _ in stream_with_tools(router=router, agent=agent,
                                         messages=[ChatMessage("user", "go")],
                                         emit=lambda e: None, result=result):
            pass

    asyncio.run(go())
    assert result.usage.prompt_tokens == 3  # 1 per turn × 3 turns
    assert result.usage.completion_tokens == 3


async def _tool_call_upstream(scope, receive, send):
    """OpenAI-style SSE where tool-call arguments arrive in fragments."""
    while True:
        msg = await receive()
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"text/event-stream")]})
    events = [
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_9",'
        '"function":{"name":"web_search","arguments":"{\\"qu"}}]}}]}\n\n',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        '"function":{"arguments":"ery\\": \\"agents\\"}"}}]}}]}\n\n',
        'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":1}}\n\n',
        "data: [DONE]\n\n",
    ]
    for i, e in enumerate(events):
        await send({"type": "http.response.body", "body": e.encode(),
                    "more_body": i < len(events) - 1})


@pytest.mark.asyncio
async def test_openrouter_reassembles_streamed_tool_call_fragments():
    """Arguments stream in as partial JSON strings and must be stitched back."""
    client = OpenRouterClient(
        api_key="k", transport=httpx.ASGITransport(app=_tool_call_upstream)
    )
    out = [c async for c in client.stream_chat(
        "openai/gpt-4o-mini", [ChatMessage("user", "hi")],
        tools=[{"type": "function", "function": {"name": "web_search"}}],
    )]

    assert out == []  # a pure tool-call turn emits no visible text
    assert len(client.last_tool_calls) == 1
    call = client.last_tool_calls[0]
    assert call.id == "call_9"
    assert call.name == "web_search"
    assert call.arguments == {"query": "agents"}  # rebuilt from two fragments
