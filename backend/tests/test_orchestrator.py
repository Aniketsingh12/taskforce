"""End-to-end orchestrator test using the mock provider (no network needed)."""

import asyncio

from app.db.schema import RunStatus
from app.orchestration import CONTENT_PIPELINE, Orchestrator


def test_content_pipeline_runs_end_to_end():
    events: list[dict] = []

    async def emit(event):
        events.append(event)

    run = asyncio.run(
        Orchestrator().run_workflow(CONTENT_PIPELINE, "test topic", emit=emit)
    )

    assert run.status == RunStatus.done
    # One trace per agent, in order.
    assert [t.agent_role for t in run.traces] == ["Researcher", "Writer", "Editor"]
    assert run.final_output  # the editor produced something
    assert run.total_tokens > 0

    types = {e["type"] for e in events}
    assert {"run_started", "agent_started", "token", "agent_completed", "run_completed"} <= types


def test_handoff_passes_prior_output_forward():
    async def emit(event):
        return None

    run = asyncio.run(
        Orchestrator().run_workflow(CONTENT_PIPELINE, "test topic", emit=emit)
    )
    writer_trace = next(t for t in run.traces if t.agent_role == "Writer")
    # The writer's input should contain the researcher's handed-off work.
    assert "Researcher" in writer_trace.input
