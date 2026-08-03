"""Context handoff — how one agent's output becomes the next agent's input.

Sequential pipelines pass the accumulated work forward. This keeps the handoff
explicit and inspectable (it shows up verbatim in each agent's trace `input`),
which is what makes runs debuggable.
"""

from __future__ import annotations

import json

from ..db.schema import AgentConfig, Trace


def build_agent_input(
    *,
    run_input: str,
    agent: AgentConfig,
    prior_traces: list[Trace],
    tool_context: str = "",
) -> str:
    """Assemble the user-facing context handed to `agent`.

    The returned string becomes the `user` message; the agent's instructions are
    the `system` message (see agent.py). Sections are plain markdown headings so
    any model can parse them.
    """
    parts: list[str] = []

    # Always start with the overall goal/input for the whole workflow.
    parts.append(f"# Workflow goal / input\n{run_input.strip() or '(none provided)'}")

    # Only hand off real output — skip agents that were skipped or produced
    # nothing, so their empty/placeholder text doesn't pollute the context.
    completed = [t for t in prior_traces if t.output.strip()]
    if completed:
        parts.append("# Work completed by previous agents")
        for t in completed:
            # When an agent produced structured output, hand the *parsed* value
            # forward as clean JSON rather than whatever prose wrapped it.
            if t.output_json is not None:
                body = json.dumps(t.output_json, indent=2)
            else:
                body = t.output.strip()
            parts.append(f"## {t.agent_role}\n{body}")

    # Surface any tool results the agent fetched before reasoning.
    if tool_context:
        parts.append(f"# Tool results\n{tool_context.strip()}")

    # Finally, restate this agent's job and the expected output format.
    parts.append(
        f"# Your task\nActing as the {agent.role}, complete your part and produce "
        f"output as {agent.output_format}. Build on the work above."
    )
    return "\n\n".join(parts)
