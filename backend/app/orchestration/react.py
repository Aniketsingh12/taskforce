"""Model-driven tool calling (the ReAct loop).

Instead of running an agent's tools on a fixed schedule, the model is handed
their JSON schemas and decides *whether* to call one, *with what arguments*, and
whether to call another after seeing the result:

    model → tool_calls? → run them → feed results back → model → … → final text

The loop is bounded by `max_tool_steps` so a model that keeps calling tools can
never spin forever. Usage is accumulated across every turn, so cost and token
counts in the trace cover the whole reasoning chain, not just the last message.

Providers that can't do tool calling (or agents set to `tool_mode="staged"`)
fall back to the simpler pre/post staging in `agent.py`.
"""

from __future__ import annotations

import json
from typing import AsyncIterator, Callable

from ..db.schema import AgentConfig
from ..models import ChatMessage, StreamResult, Usage
from ..tools import get_tool

EmitFn = Callable[[dict], object]


async def _maybe_await(value: object) -> None:
    if hasattr(value, "__await__"):
        await value  # type: ignore[misc]


def callable_tools(agent: AgentConfig) -> list:
    """The agent's model-callable tools (post-stage sinks are not offered)."""
    specs = [get_tool(n) for n in agent.tools]
    return [s for s in specs if s is not None and s.stage == "pre"]


async def _execute(call, emit: EmitFn, agent_id: str) -> str:
    """Run one requested tool call and return its result as text."""
    spec = get_tool(call.name)
    if spec is None:
        return f"[no such tool: {call.name}]"
    # Tools take a single string argument today; pull the first schema property
    # (usually "query") out of whatever the model supplied.
    args = call.arguments or {}
    payload = args.get("query")
    if payload is None:
        payload = next((v for v in args.values() if isinstance(v, str)), "")
    await _maybe_await(emit({
        "type": "tool_call", "agent_id": agent_id,
        "tool": call.name, "arguments": args,
    }))
    try:
        return await spec.fn(payload)
    except Exception as exc:  # noqa: BLE001 - a broken tool shouldn't kill the agent
        return f"[tool '{call.name}' error: {exc}]"


async def stream_with_tools(
    *,
    router,
    agent: AgentConfig,
    messages: list[ChatMessage],
    emit: EmitFn,
    result: StreamResult,
) -> AsyncIterator[str]:
    """Stream the agent's answer, letting the model call tools along the way.

    Yields only the text of the FINAL answer turn — intermediate turns that just
    request tools aren't shown as the deliverable (their tool activity is
    surfaced through `tool_call` events instead).
    """
    specs = callable_tools(agent)
    schemas = [s.to_schema() for s in specs] or None
    called: list[str] = []
    total = Usage()

    for step in range(max(1, agent.max_tool_steps)):
        turn = StreamResult()
        text_parts: list[str] = []
        # Only the last allowed step runs without tools, forcing a final answer.
        offer = schemas if step < agent.max_tool_steps - 1 else None

        async for chunk in router.stream(
            agent.model_provider, agent.model_name, messages,
            result=turn, fallback=agent.fallback_model, tools=offer,
        ):
            text_parts.append(chunk)
            yield chunk

        # Accumulate usage/cost across every turn in the chain.
        total.prompt_tokens += turn.usage.prompt_tokens
        total.completion_tokens += turn.usage.completion_tokens
        total.cost_usd = round(total.cost_usd + turn.usage.cost_usd, 6)
        result.model = turn.model

        if not turn.tool_calls:
            break  # the model produced its final answer

        # Record the model's request, run the tools, feed the results back.
        messages.append(ChatMessage(
            role="assistant", content="".join(text_parts), tool_calls=turn.tool_calls,
        ))
        for call in turn.tool_calls:
            output = await _execute(call, emit, agent.id)
            called.append(call.name)
            messages.append(ChatMessage(
                role="tool", content=output,
                tool_call_id=call.id, name=call.name,
            ))

    # Everything the caller needs goes on its own `result` object — never on
    # module or router state, so parallel agents can't clobber each other.
    result.usage = total
    result.tool_calls = []
    result.tools_called = called


def parse_arguments(raw: str | dict) -> dict:
    """Tolerantly turn a model's argument blob into a dict."""
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
