"""Regression tests for tool staging and the observability split."""

import asyncio

from app.api.stats import stats
from app.db.schema import AgentConfig, RunStatus, WorkflowConfig
from app.db.store import store
from app.orchestration import Orchestrator
from app.tools import get_tool
from app.tools.file_tool import OUTPUT_DIR


def _run(workflow, text):
    return asyncio.run(Orchestrator().run_workflow(workflow, text, emit=lambda e: None))


def test_save_file_writes_agent_output_not_run_input():
    """save_file is a post-stage tool, so the file holds what the agent PRODUCED.

    It previously ran before the model with the run input as its argument, so
    the "deliverable" on disk was just the topic string.
    """
    wf = WorkflowConfig(
        id="test-save-file",
        name="Save File Test",
        agents=[AgentConfig(role="Editor", order=0,
                            instructions="Edit the piece.", tools=["save_file"])],
    )
    run_input = "a topic that must NOT be the saved deliverable"
    run = _run(wf, run_input)

    assert run.status == RunStatus.done
    saved = (OUTPUT_DIR / "deliverable.md").read_text(encoding="utf-8")
    assert saved == run.final_output      # the agent's real output
    assert saved != run_input             # not the input that used to land here
    # The tool still shows up in the trace for observability.
    assert "save_file" in run.traces[0].tools_called


def test_staged_mode_injects_pre_tool_output_as_context():
    """tool_mode="staged" keeps the legacy fixed schedule: run tool, then model."""
    assert get_tool("web_search").stage == "pre"
    assert get_tool("save_file").stage == "post"

    wf = WorkflowConfig(
        id="test-pre-tool",
        name="Pre Tool Test",
        agents=[AgentConfig(role="Researcher", order=0, tool_mode="staged",
                            instructions="Research it.", tools=["web_search"])],
    )
    run = _run(wf, "multi-agent systems")
    trace = run.traces[0]
    assert "web_search" in trace.tools_called
    # Pre-tool output is injected into the prompt the model saw.
    assert "Tool results" in trace.input


def test_auto_mode_lets_the_model_call_the_tool_itself():
    """tool_mode="auto" (the default) runs the ReAct loop.

    Nothing is pre-injected; the model asks for the tool, sees the result, and
    only then writes its answer.
    """
    wf = WorkflowConfig(
        id="test-react",
        name="ReAct Test",
        agents=[AgentConfig(role="Researcher", order=0,
                            instructions="Research it.", tools=["web_search"])],
    )
    run = _run(wf, "multi-agent systems")
    trace = run.traces[0]

    # The model chose the tool — it wasn't scheduled for it.
    assert "web_search" in trace.tools_called
    assert "Tool results" not in trace.input
    # Usage is summed across both turns of the exchange, not just the last.
    assert trace.prompt_tokens > 0 and trace.completion_tokens > 0


def test_skipped_agents_are_excluded_from_the_local_api_split():
    """A skipped agent never ran, so it must not count as an API agent."""
    wf = WorkflowConfig(
        id="test-skip-stats",
        name="Skip Stats Test",
        agents=[
            AgentConfig(role="Classifier", order=0, instructions="Classify."),
            # Condition can't match the mock Classifier's output → skipped.
            AgentConfig(role="Ghost", order=1, instructions="Never runs.",
                        condition="this-phrase-never-appears"),
        ],
    )
    store.save_workflow(wf)
    run = _run(wf, "anything")

    skipped = [t for t in run.traces if t.status == RunStatus.skipped]
    assert len(skipped) == 1, "expected the conditional agent to be skipped"

    s = stats()
    b = s["cost_breakdown"]
    # The skipped agent lands in its own bucket, not in local or API.
    assert b["skipped_agents"] >= 1
    assert b["local_agents"] + b["api_agents"] + b["skipped_agents"] == sum(
        len(r.traces) for r in store.list_runs()
    )
