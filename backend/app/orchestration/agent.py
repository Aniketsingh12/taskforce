"""Single-agent execution: run tools, call the model, stream output, record usage.

This is the unit the engine schedules. One call to `run_agent` = one agent doing
its job once and returning a fully populated Trace.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Callable

from ..db.schema import AgentConfig, RunStatus, Trace
from ..models import ChatMessage, StreamResult, get_router
from ..tools import get_tool
from .handoff import build_agent_input
from .output import JSON_REPAIR_NUDGE, extract_json
from .react import callable_tools, stream_with_tools

# emit(event: dict) -> awaitable | None  — pushed to the live run view
EmitFn = Callable[[dict], object]


async def _run_tools(agent: AgentConfig, payload: str, stage: str) -> tuple[str, list[str]]:
    """Run the agent's tools for one stage and collect their output.

    `stage="pre"` tools get the run input and feed the prompt; `stage="post"`
    tools get the agent's finished output (see ToolSpec). MVP behaviour: each
    tool is invoked once. The full version replaces this with a model-driven
    tool-calling loop (the model decides which tool to call and with what args).
    """
    chunks: list[str] = []   # human-readable tool outputs to inject into context
    called: list[str] = []   # names recorded in the trace for observability
    for name in agent.tools:
        spec = get_tool(name)
        if spec is None or spec.stage != stage:
            continue  # not this stage (or tool removed/renamed) — skip
        try:
            result = await spec.fn(payload)
        except Exception as exc:  # noqa: BLE001 - a broken tool shouldn't fail the agent
            result = f"[tool '{name}' error: {exc}]"
        chunks.append(f"{name}: {result}")
        called.append(name)
    return "\n\n".join(chunks), called


async def run_agent(
    *,
    run_id: str,
    agent: AgentConfig,
    run_input: str,
    prior_traces: list[Trace],   # everything completed before this agent
    emit: EmitFn,
) -> Trace:
    router = get_router()
    started = time.perf_counter()  # for latency measurement

    # 1) In "auto" mode the model calls tools itself, so nothing is pre-injected;
    #    in "staged" mode pre-tools run now and their output becomes context.
    react_mode = agent.tool_mode == "auto" and bool(callable_tools(agent))
    if react_mode:
        tool_context, called = "", []
    else:
        tool_context, called = await _run_tools(agent, run_input, "pre")
    user_content = build_agent_input(
        run_input=run_input,
        agent=agent,
        prior_traces=prior_traces,
        tool_context=tool_context,
    )
    # The agent's own instructions become the system prompt.
    messages = [
        ChatMessage(role="system", content=agent.instructions),
        ChatMessage(role="user", content=user_content),
    ]

    # 2) Open the trace (status=running) and tell the UI this agent has started.
    trace = Trace(
        run_id=run_id,
        agent_id=agent.id,
        agent_role=agent.role,
        input=user_content,
        tools_called=called,
        status=RunStatus.running,
    )
    await _maybe_await(emit({"type": "agent_started", "agent_id": agent.id,
                             "role": agent.role, "order": agent.order}))

    # 3) Stream the model response token-by-token, forwarding each chunk live.
    #    `result` is owned by this call, so parallel agents never share usage
    #    state on the router singleton.
    #
    #    Each attempt is bounded by `timeout_seconds` and retried up to
    #    `max_retries` times. A retry restarts the response from scratch, so the
    #    UI is told to discard whatever the failed attempt had already streamed.
    attempts = max(1, agent.max_retries + 1)
    result = StreamResult()
    output_parts: list[str] = []
    parsed_json: object | None = None
    parse_error: str | None = None
    repair_hint: str | None = None  # set when a JSON reply failed to parse

    for attempt in range(attempts):
        result = StreamResult()
        output_parts = []
        try:
            async with asyncio.timeout(agent.timeout_seconds):
                # A retry must start from the original prompt, not one already
                # carrying a half-finished tool exchange.
                turn_messages = list(messages)
                if repair_hint:
                    # Correct the model rather than repeating the same request.
                    turn_messages.append(ChatMessage(role="user", content=repair_hint))
                if react_mode:
                    stream = stream_with_tools(
                        router=router, agent=agent, messages=turn_messages,
                        emit=emit, result=result,
                    )
                else:
                    stream = router.stream(
                        agent.model_provider, agent.model_name, turn_messages,
                        result=result, fallback=agent.fallback_model,
                    )
                async for chunk in stream:
                    output_parts.append(chunk)
                    await _maybe_await(
                        emit({"type": "token", "agent_id": agent.id, "text": chunk})
                    )

            # A JSON agent that returned prose hasn't really succeeded — spend a
            # retry on a correction before accepting unparseable output.
            if agent.output_format == "json":
                parsed_json, parse_error = extract_json("".join(output_parts))
                if parse_error and attempt < attempts - 1:
                    repair_hint = JSON_REPAIR_NUDGE
                    await _maybe_await(emit({
                        "type": "agent_retry", "agent_id": agent.id, "role": agent.role,
                        "attempt": attempt + 1, "of": attempts,
                        "reason": f"output was not valid JSON ({parse_error})",
                    }))
                    continue
            break  # attempt succeeded
        except (Exception, asyncio.TimeoutError) as exc:  # noqa: BLE001
            if attempt == attempts - 1:
                raise  # out of attempts → fail the agent (and the run)
            reason = "timed out" if isinstance(exc, asyncio.TimeoutError) else str(exc)
            await _maybe_await(emit({
                "type": "agent_retry", "agent_id": agent.id, "role": agent.role,
                "attempt": attempt + 1, "of": attempts, "reason": reason,
            }))

    # 4) Close the trace with the full output and the usage the router recorded
    #    (which model actually ran, token counts, cost, and measured latency).
    trace.output = "".join(output_parts)
    trace.output_json = parsed_json
    trace.parse_error = parse_error

    # 4b) Post-stage tools (output sinks) receive what this agent actually
    #     produced — this is what makes save_file write the real deliverable.
    _, post_called = await _run_tools(agent, trace.output, "post")
    # In auto mode the loop reports which tools the model chose to run.
    trace.tools_called = called + result.tools_called + post_called

    trace.model_used = result.model
    trace.prompt_tokens = result.usage.prompt_tokens
    trace.completion_tokens = result.usage.completion_tokens
    trace.cost_usd = result.usage.cost_usd
    trace.latency_ms = int((time.perf_counter() - started) * 1000)
    trace.status = RunStatus.done

    await _maybe_await(emit({"type": "agent_completed", "trace": trace.model_dump(mode="json")}))
    return trace


async def _maybe_await(value: object) -> None:
    # Support both sync and async emit callbacks (see engine.py).
    if hasattr(value, "__await__"):
        await value  # type: ignore[misc]
