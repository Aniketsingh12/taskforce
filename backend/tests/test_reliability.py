"""Retries, timeouts, partial-stream safety, and crash recovery."""

import asyncio

import pytest

from app.db.schema import AgentConfig, Run, RunStatus, Trace, WorkflowConfig
from app.db.store import store
from app.models import ChatMessage, ModelRouter, StreamResult
from app.models.base import ModelClient, Usage
from app.orchestration.agent import run_agent


class FlakyClient(ModelClient):
    """Fails the first N attempts, then succeeds."""

    provider = "flaky"
    attempts = 0

    def __init__(self, fail_times: int = 1, fail_after_chunks: int = 0) -> None:
        super().__init__()
        self.fail_times = fail_times
        self.fail_after_chunks = fail_after_chunks

    async def stream_chat(self, model, messages):
        type(self).attempts += 1
        for i in range(self.fail_after_chunks):
            yield f"partial{i} "
        if type(self).attempts <= self.fail_times:
            raise RuntimeError("upstream blew up")
        yield "recovered output"
        self.last_usage = Usage(prompt_tokens=5, completion_tokens=2, cost_usd=0.0)


def _router_with(client_factory) -> ModelRouter:
    r = ModelRouter()
    r._factories = {**r._factories, "flaky": client_factory}
    return r


def test_agent_retries_a_failing_model_then_succeeds(monkeypatch):
    FlakyClient.attempts = 0
    router = _router_with(lambda: FlakyClient(fail_times=1))
    monkeypatch.setattr("app.orchestration.agent.get_router", lambda: router)

    agent = AgentConfig(role="Writer", instructions="write",
                        model_provider="flaky", model_name="m",
                        max_retries=2, fallback_model="flaky:m")
    events = []

    trace = asyncio.run(run_agent(
        run_id="r1", agent=agent, run_input="topic",
        prior_traces=[], emit=lambda e: events.append(e),
    ))

    assert trace.status == RunStatus.done
    assert trace.output == "recovered output"
    # The failed attempt was announced so the UI can reset its buffer.
    retries = [e for e in events if e["type"] == "agent_retry"]
    assert len(retries) == 1 and retries[0]["attempt"] == 1


def test_agent_gives_up_after_max_retries(monkeypatch):
    FlakyClient.attempts = 0
    router = _router_with(lambda: FlakyClient(fail_times=99))
    monkeypatch.setattr("app.orchestration.agent.get_router", lambda: router)

    agent = AgentConfig(role="Writer", instructions="write",
                        model_provider="flaky", model_name="m",
                        max_retries=1, fallback_model="flaky:m")

    with pytest.raises(RuntimeError):
        asyncio.run(run_agent(run_id="r2", agent=agent, run_input="t",
                              prior_traces=[], emit=lambda e: None))
    assert FlakyClient.attempts == 2  # first try + one retry


def test_retry_discards_partial_output_instead_of_splicing(monkeypatch):
    """A stream that dies mid-response must not be glued to the retry's output."""
    FlakyClient.attempts = 0
    router = _router_with(lambda: FlakyClient(fail_times=1, fail_after_chunks=2))
    monkeypatch.setattr("app.orchestration.agent.get_router", lambda: router)

    agent = AgentConfig(role="Writer", instructions="write",
                        model_provider="flaky", model_name="m",
                        max_retries=1, fallback_model="flaky:m")
    trace = asyncio.run(run_agent(run_id="r3", agent=agent, run_input="t",
                                  prior_traces=[], emit=lambda e: None))
    # Only the successful attempt's text survives — the "partial0 partial1 "
    # from the failed attempt is gone, and appears exactly once from the retry.
    assert trace.output == "partial0 partial1 recovered output"
    assert trace.output.count("partial0") == 1


def test_timeout_bounds_a_hanging_model(monkeypatch):
    class HangingClient(ModelClient):
        provider = "hang"

        async def stream_chat(self, model, messages):
            await asyncio.sleep(30)
            yield "never"

    router = ModelRouter()
    router._factories = {**router._factories, "hang": HangingClient}
    monkeypatch.setattr("app.orchestration.agent.get_router", lambda: router)

    agent = AgentConfig(role="Slow", instructions="x",
                        model_provider="hang", model_name="m",
                        max_retries=0, timeout_seconds=0.2,
                        fallback_model="hang:m")

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run_agent(run_id="r4", agent=agent, run_input="t",
                              prior_traces=[], emit=lambda e: None))


def test_interrupted_runs_are_reconciled_on_startup():
    """A run persisted as `running` when the process died must not stay that way."""
    stuck = Run(workflow_id="wf-x", workflow_name="Crashed", status=RunStatus.running)
    stuck.traces.append(Trace(run_id=stuck.id, agent_id="a", agent_role="A"))
    store.save_run(stuck)

    assert store.get_run(stuck.id).status == RunStatus.running
    store.reconcile_interrupted_runs()

    recovered = store.get_run(stuck.id)
    assert recovered.status == RunStatus.failed
    assert "Interrupted" in recovered.error
