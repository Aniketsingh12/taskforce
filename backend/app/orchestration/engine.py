"""Orchestration engine.

Executes a workflow as ordered **stages**:
- agents with `parallel_group = None` are their own sequential stage;
- agents sharing a `parallel_group` run concurrently within one stage.

Each agent may carry a `condition`; if unmet, the agent is skipped. The
node/edge stage model mirrors a LangGraph `StateGraph`, so LangGraph can be
swapped in later without changing the API or the live event contract.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

from ..db.schema import AgentConfig, Run, RunStatus, Trace, WorkflowConfig
from ..db.store import store
from .agent import run_agent

# An emit function receives one event dict per orchestration step. It can be
# sync or async; the live UI passes the WebSocket broker's emitter here.
EmitFn = Callable[[dict], object]


async def _noop_emit(_event: dict) -> None:
    # Default emitter — used by the CLI/tests where nobody is listening.
    return None


def condition_met(condition: str | None, prior_traces: list[Trace]) -> bool:
    """A condition passes if its phrase appears in any prior output.

    Prefix with '!' to invert (run only when the phrase is absent).
    Example: an Escalation agent with condition="escalate" runs only when an
    earlier agent's output contains the word "escalate".
    """
    if not condition:
        return True  # no condition → the agent always runs
    invert = condition.startswith("!")
    needle = (condition[1:] if invert else condition).strip().lower()
    # Search across everything produced so far, case-insensitively.
    haystack = "\n".join(t.output for t in prior_traces).lower()
    present = needle in haystack
    return (not present) if invert else present


def _build_stages(agents: list[AgentConfig]) -> list[list[AgentConfig]]:
    """Group agents into execution stages.

    Agents that share a `parallel_group` collapse into one stage (they run
    together); every other agent is a stage of one. Stages are then sorted by
    the lowest `order` they contain, so the sequence is deterministic.
    """
    groups: dict[object, list[AgentConfig]] = {}
    for a in agents:
        # Key by group id when parallel, else by the agent's own id (unique).
        key = ("group", a.parallel_group) if a.parallel_group is not None else ("solo", a.id)
        groups.setdefault(key, []).append(a)
    return sorted(groups.values(), key=lambda ags: min(x.order for x in ags))


class Orchestrator:
    """Runs a workflow end to end, streaming events and persisting the run."""

    async def run_workflow(
        self,
        workflow: WorkflowConfig,
        run_input: str,
        *,
        run_id: str | None = None,        # pre-allocated id so callers can return it immediately
        trigger_source: str = "manual",   # manual | webhook | schedule
        emit: EmitFn = _noop_emit,
    ) -> Run:
        # 1) Create the run record and persist it as "running" right away, so it
        #    shows up in history even if something fails mid-flight.
        run = Run(
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            status=RunStatus.running,
            trigger_source=trigger_source,
            input=run_input,
        )
        if run_id:
            run.id = run_id
        store.save_run(run)

        # 2) Announce the run and its agent list so the UI can draw the pipeline
        #    before any token arrives.
        ordered = sorted(workflow.agents, key=lambda a: a.order)
        await _maybe_await(emit({
            "type": "run_started",
            "run_id": run.id,
            "workflow_name": workflow.name,
            "trigger_source": trigger_source,
            "agents": [
                {"id": a.id, "role": a.role, "order": a.order,
                 "parallel_group": a.parallel_group,
                 "model": f"{a.model_provider}:{a.model_name}"}
                for a in ordered
            ],
        }))

        try:
            # 3) Walk the stages in order.
            for stage in _build_stages(ordered):
                # All agents in a parallel stage must see the SAME prior context
                # (the work done before this stage), not each other's output.
                snapshot = list(run.traces)

                running: list[AgentConfig] = []
                for agent in stage:
                    if condition_met(agent.condition, snapshot):
                        running.append(agent)
                    else:
                        # Record the skip so it appears in the trace/history,
                        # then tell the UI to grey the node out.
                        skipped = Trace(
                            run_id=run.id, agent_id=agent.id, agent_role=agent.role,
                            output="", status=RunStatus.skipped,
                        )
                        run.traces.append(skipped)
                        await _maybe_await(emit({
                            "type": "agent_skipped", "agent_id": agent.id,
                            "role": agent.role, "condition": agent.condition,
                        }))

                if not running:
                    continue  # whole stage was conditional and skipped

                # 4) Run every agent in this stage concurrently. For a solo stage
                #    that's just one coroutine; for a parallel group it's many.
                stage_traces = await asyncio.gather(*[
                    run_agent(
                        run_id=run.id, agent=agent, run_input=run_input,
                        prior_traces=snapshot, emit=emit,
                    )
                    for agent in running
                ])

                # 5) Fold the stage's results back into the run totals.
                for trace in stage_traces:
                    run.traces.append(trace)
                    run.total_cost = round(run.total_cost + trace.cost_usd, 6)
                    run.total_tokens += trace.prompt_tokens + trace.completion_tokens

                # 6) Enforce the optional per-workflow spend cap.
                if workflow.cost_cap and run.total_cost > workflow.cost_cap:
                    raise RuntimeError(
                        f"Cost cap ${workflow.cost_cap} exceeded "
                        f"(spent ${run.total_cost})."
                    )

            # 7) The deliverable is the last agent that actually produced output.
            done = [t for t in run.traces if t.status == RunStatus.done and t.output]
            run.final_output = done[-1].output if done else ""
            run.status = RunStatus.done
        except Exception as exc:  # noqa: BLE001 - any failure marks the run failed
            run.status = RunStatus.failed
            run.error = str(exc)
            await _maybe_await(emit({"type": "run_failed", "run_id": run.id, "error": str(exc)}))
        finally:
            # Always stamp the end time and persist the final state.
            run.finished_at = datetime.now(timezone.utc)
            store.save_run(run)

        if run.status == RunStatus.done:
            await _maybe_await(emit({"type": "run_completed", "run": run.model_dump(mode="json")}))
        return run


async def _maybe_await(value: object) -> None:
    # `emit` may be a plain function or a coroutine function; support both by
    # awaiting only when the return value is awaitable.
    if hasattr(value, "__await__"):
        await value  # type: ignore[misc]
