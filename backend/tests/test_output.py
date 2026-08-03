"""Structured-output extraction: digging JSON out of whatever the model said."""

import asyncio

from app.db.schema import AgentConfig, WorkflowConfig
from app.orchestration import Orchestrator
from app.orchestration.output import extract_json


def test_parses_bare_json():
    value, err = extract_json('{"fit_score": 8, "reason": "good"}')
    assert err is None and value["fit_score"] == 8


def test_parses_fenced_json_block():
    raw = 'Here is the result:\n```json\n{"category": "billing"}\n```\nHope that helps!'
    value, err = extract_json(raw)
    assert err is None and value == {"category": "billing"}


def test_parses_unfenced_json_wrapped_in_prose():
    raw = 'Sure! {"score": 3, "ok": true} — let me know if you need more.'
    value, err = extract_json(raw)
    assert err is None and value == {"score": 3, "ok": True}


def test_parses_json_array():
    value, err = extract_json("```\n[1, 2, 3]\n```")
    assert err is None and value == [1, 2, 3]


def test_braces_inside_strings_do_not_end_the_object():
    raw = 'Result: {"note": "use {curly} braces", "n": 1} done'
    value, err = extract_json(raw)
    assert err is None
    assert value["note"] == "use {curly} braces" and value["n"] == 1


def test_reports_failure_instead_of_guessing():
    value, err = extract_json("I could not complete that request.")
    assert value is None and "no valid JSON" in err

    value, err = extract_json("")
    assert value is None and err == "empty output"


def test_json_agent_populates_parsed_output_on_the_trace():
    """An output_format="json" agent exposes the parsed value, not just text."""
    wf = WorkflowConfig(
        id="test-json-out",
        name="JSON Out",
        agents=[AgentConfig(role="Classifier", order=0, output_format="json",
                            instructions="Categorize the ticket.")],
    )
    run = asyncio.run(Orchestrator().run_workflow(wf, "refund please", emit=lambda e: None))
    trace = run.traces[0]

    assert trace.parse_error is None
    assert isinstance(trace.output_json, dict)
    assert trace.output_json["category"] == "billing"
    # The raw text is still preserved alongside the parsed value.
    assert trace.output.strip().startswith("{")


def test_structured_output_is_handed_forward_as_clean_json():
    """The next agent sees parsed JSON, not the prose that wrapped it."""
    wf = WorkflowConfig(
        id="test-json-handoff",
        name="JSON Handoff",
        agents=[
            AgentConfig(role="Classifier", order=0, output_format="json",
                        instructions="Categorize."),
            AgentConfig(role="Responder", order=1, instructions="Reply."),
        ],
    )
    run = asyncio.run(Orchestrator().run_workflow(wf, "refund", emit=lambda e: None))
    responder = next(t for t in run.traces if t.agent_role == "Responder")
    # Re-serialised with indentation → came from the parsed value.
    assert '"category": "billing"' in responder.input
