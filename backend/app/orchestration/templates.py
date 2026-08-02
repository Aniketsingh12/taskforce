"""Pre-built workflow templates — cloneable starting points.

Demonstrates every execution mode:
- Content Pipeline   — sequential handoff
- Research Report    — parallel researchers (one `parallel_group`)
- Lead Qualification — sequential enrichment → scoring → outreach → CRM
- Support Triage     — conditional escalation (runs only if flagged)
"""

from __future__ import annotations

from ..db.schema import AgentConfig, WorkflowConfig


def _agent(role, order, instructions, **kw) -> AgentConfig:
    return AgentConfig(role=role, order=order, instructions=instructions, **kw)


CONTENT_PIPELINE = WorkflowConfig(
    id="tpl-content-pipeline",
    name="Content Pipeline",
    description="Research a topic, draft an article, and edit it to publish-ready.",
    is_template=True,
    agents=[
        _agent("Researcher", 0,
               "You are a meticulous researcher. Gather key facts, sources, and "
               "angles on the topic. Produce concise notes the writer can build "
               "on, and cite where claims come from.",
               tools=["web_search"]),
        _agent("Writer", 1,
               "You are a skilled writer. Using the researcher's notes, write a "
               "clear, engaging draft with a strong intro, structured body, and a "
               "memorable conclusion."),
        _agent("Editor", 2,
               "You are a sharp editor. Tighten the draft, fix flow and clarity, "
               "remove redundancy, and deliver the final publish-ready piece.",
               tools=["save_file"]),
    ],
)

RESEARCH_REPORT = WorkflowConfig(
    id="tpl-research-report",
    name="Research Report",
    description="Plan a question, research subtopics in parallel, synthesize, and fact-check.",
    is_template=True,
    agents=[
        _agent("Planner", 0,
               "Break the research question into 3 focused subtopics for the "
               "research team. Output a short numbered plan."),
        # These three run concurrently (same parallel_group).
        _agent("Researcher: Market", 1, parallel_group=1, tools=["web_search"],
               instructions="Research the MARKET/industry angle of the subtopic. Return concise findings with sources."),
        _agent("Researcher: Technical", 1, parallel_group=1, tools=["web_search"],
               instructions="Research the TECHNICAL angle. Return concise findings with sources."),
        _agent("Researcher: Risks", 1, parallel_group=1, tools=["web_search"],
               instructions="Research RISKS and counter-arguments. Return concise findings with sources."),
        _agent("Synthesizer", 2,
               "Combine the three researchers' findings into one coherent, "
               "well-structured report with clear sections."),
        _agent("Fact-checker", 3, tools=["web_search"],
               instructions="Verify the report's key claims and flag anything unsupported. Output the final cited report."),
    ],
)

LEAD_QUALIFICATION = WorkflowConfig(
    id="tpl-lead-qualification",
    name="Lead Qualification",
    description="Enrich a lead, score fit, draft outreach, and log to CRM.",
    is_template=True,
    agents=[
        _agent("Enrichment", 0, tools=["web_search"],
               instructions="Look up the company/lead and summarize size, industry, and signals."),
        _agent("Scorer", 1,
               "Rate the lead's fit 1–10 with a one-line justification, as JSON.",
               output_format="json"),
        _agent("Personalizer", 2,
               "Draft a short, personalized outreach email based on the enrichment and score."),
        _agent("CRM", 3, tools=["save_file"],
               instructions="Format a CRM log entry (lead, score, next step) and save it."),
    ],
)

SUPPORT_TRIAGE = WorkflowConfig(
    id="tpl-support-triage",
    name="Support Triage",
    description="Classify a ticket, retrieve docs, draft a reply, escalate hard ones.",
    is_template=True,
    agents=[
        _agent("Classifier", 0,
               "Categorize the support ticket and rate its difficulty. If it is "
               "complex or high-risk, include the word 'escalate' in your output.",
               output_format="json"),
        _agent("Retriever", 1, tools=["web_search"],
               instructions="Find the most relevant documentation for this ticket."),
        _agent("Responder", 2,
               "Draft a clear, friendly reply to the customer using the docs."),
        # Runs only when the classifier flagged escalation.
        _agent("Escalation", 3, condition="escalate",
               instructions="Summarize why this needs a human and to which team it should go."),
    ],
)


def default_templates() -> list[WorkflowConfig]:
    return [CONTENT_PIPELINE, RESEARCH_REPORT, LEAD_QUALIFICATION, SUPPORT_TRIAGE]
