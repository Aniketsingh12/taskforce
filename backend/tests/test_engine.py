"""Parallel and conditional execution tests (mock provider, no network)."""

import asyncio

from app.db.schema import RunStatus
from app.models import ChatMessage, ModelRouter, StreamResult
from app.orchestration import Orchestrator
from app.orchestration.engine import condition_met
from app.orchestration.templates import RESEARCH_REPORT, SUPPORT_TRIAGE
from app.db.schema import Trace


def _run(workflow, text):
    return asyncio.run(Orchestrator().run_workflow(workflow, text, emit=lambda e: None))


def test_parallel_researchers_all_run():
    run = _run(RESEARCH_REPORT, "impact of AI agents")
    assert run.status == RunStatus.done
    roles = [t.agent_role for t in run.traces]
    # All three parallel researchers plus planner, synthesizer, fact-checker.
    assert roles.count("Researcher: Market") == 1
    assert "Researcher: Technical" in roles
    assert "Researcher: Risks" in roles
    assert roles[0] == "Planner"  # planner runs before the parallel stage
    assert roles[-1] == "Fact-checker"


def test_condition_met_helper():
    traces = [Trace(run_id="r", agent_id="a", agent_role="Classifier", output="please escalate this")]
    assert condition_met("escalate", traces) is True
    assert condition_met("refund", traces) is False
    assert condition_met("!refund", traces) is True   # inverted: phrase absent
    assert condition_met(None, traces) is True         # no condition → always


def test_support_triage_escalates_when_flagged():
    # The mock Classifier emits "escalate", so the Escalation agent should run.
    run = _run(SUPPORT_TRIAGE, "customer wants a refund")
    statuses = {t.agent_role: t.status for t in run.traces}
    assert statuses["Escalation"] == RunStatus.done


def test_per_agent_fallback_overrides_the_global_chain():
    """An agent's `fallback_model` ("provider:model") wins over settings.

    Routes to openrouter with no API key configured, which fails immediately and
    offline — a deterministic trigger for the fallback path (unlike ollama,
    which may actually be running on the dev machine).
    """
    router = ModelRouter()

    async def go(fallback):
        result = StreamResult()
        async for _ in router.stream(
            "openrouter", "openai/gpt-4o-mini", [ChatMessage("user", "hi")],
            result=result, fallback=fallback,
        ):
            pass
        return result.model

    # The agent's explicit choice is used...
    assert asyncio.run(go("mock:my-backup")) == "mock:my-backup (fallback)"
    # ...and without one, the global chain (settings) still applies.
    assert asyncio.run(go(None)) == "mock:mock-default (fallback)"


def test_parallel_streams_get_isolated_usage():
    """Two agents streaming through the shared router at once must each read
    back their OWN model + usage — never leak state into one another.
    """
    router = ModelRouter()  # a singleton in prod; shared here on purpose

    async def consume(model: str, messages: list[ChatMessage], result: StreamResult):
        async for _ in router.stream("mock", model, messages, result=result):
            pass  # mock sleeps per word, so the two streams interleave

    async def go():
        big = StreamResult()
        small = StreamResult()
        big_msgs = [ChatMessage("system", "research"), ChatMessage("user", "x" * 400)]
        small_msgs = [ChatMessage("system", "editor"), ChatMessage("user", "y" * 12)]
        await asyncio.gather(
            consume("big-model", big_msgs, big),
            consume("small-model", small_msgs, small),
        )
        return big, small

    big, small = asyncio.run(go())
    # Each result names the model from its own call.
    assert big.model == "mock:big-model"
    assert small.model == "mock:small-model"
    # And carries its own prompt size — no cross-contamination under concurrency.
    assert big.usage.prompt_tokens > small.usage.prompt_tokens > 0
