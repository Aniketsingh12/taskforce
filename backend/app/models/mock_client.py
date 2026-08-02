"""Mock model client — lets the whole pipeline run with zero setup.

Produces deterministic, role-aware streaming text so the live run view, traces,
and cost accounting all work without Ollama installed or any API key. This is
what powers the out-of-the-box demo and the test suite.
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator

from .base import ChatMessage, ModelClient, Usage, estimate_cost, estimate_tokens


def _canned_response(messages: list[ChatMessage]) -> str:
    system = next((m.content for m in messages if m.role == "system"), "")
    user = next((m.content for m in reversed(messages) if m.role == "user"), "")

    # The handoff builder writes "Acting as the <Role>," into the user message,
    # which is a far more reliable signal than keyword-matching instructions
    # (a Writer's instructions legitimately mention the "researcher").
    acting = re.search(r"Acting as the ([A-Za-z /]+?),", user)
    role_hint = (acting.group(1) if acting else system).lower()

    if "research" in role_hint:
        return (
            "Here are the key findings from my research:\n"
            f"- The topic relates to: {user[:120].strip()}\n"
            "- Source A: industry reports show steady growth.\n"
            "- Source B: practitioners highlight three recurring themes.\n"
            "- Source C: notable counter-argument worth addressing.\n"
            "I've gathered enough context to hand off to the writer."
        )
    if "writ" in role_hint:
        return (
            "# Draft\n\n"
            "Based on the research handed to me, here is a first draft. It opens "
            "with the core thesis, develops three supporting points, and closes "
            "with a clear takeaway. Tone is confident and concrete.\n\n"
            "This draft is ready for editing."
        )
    if "edit" in role_hint or "review" in role_hint:
        return (
            "Edited version: tightened the intro, removed two redundant "
            "sentences, fixed pacing in the middle section, and sharpened the "
            "conclusion. The piece now reads cleanly and is publish-ready."
        )
    if "seo" in role_hint:
        return (
            "SEO pass complete: added a keyword-rich title, a meta description "
            "under 155 chars, three H2 headings, and internal-link suggestions."
        )
    if "plan" in role_hint:
        return (
            "Research plan:\n1. Market and adoption trends.\n"
            "2. Technical approach and trade-offs.\n3. Risks and counter-arguments."
        )
    if "synthes" in role_hint:
        return (
            "# Synthesized report\nCombining the parallel research streams: the "
            "market is growing, the technical approach is viable with caveats, and "
            "the main risks are addressable. Sections follow with supporting points."
        )
    if "fact" in role_hint:
        return (
            "Fact-check complete: 8 of 9 claims are supported by the cited sources; "
            "one was softened for accuracy. Final cited report is ready."
        )
    if "enrich" in role_hint:
        return (
            "Enrichment: Acme Co — ~200 employees, B2B SaaS, recently raised a "
            "Series B and is hiring in ops. Strong buying signals."
        )
    if "scor" in role_hint:
        return '{"fit_score": 8, "reason": "ICP match with active buying signals"}'
    if "personal" in role_hint:
        return (
            "Subject: Quick idea for Acme's ops team\n\nHi — saw you're scaling ops "
            "post-Series B. We help teams like yours automate the busywork. Worth a "
            "15-min chat next week?"
        )
    if "crm" in role_hint:
        return "CRM entry: Acme Co | fit 8/10 | next step: send intro email. Logged."
    if "classif" in role_hint:
        return '{"category": "billing", "difficulty": "high", "note": "escalate"}'
    if "retriev" in role_hint:
        return (
            "Retrieved docs: 'Billing FAQ', 'Refund policy', 'Plan changes'. "
            "Most relevant: refund policy section 3."
        )
    if "respon" in role_hint:
        return (
            "Hi there — thanks for reaching out! Based on our refund policy, here's "
            "how we can resolve this for you. Let me know if that works."
        )
    if "escal" in role_hint:
        return (
            "Escalation: high-value billing dispute requiring a refund exception. "
            "Route to the Billing Operations team with full context attached."
        )
    return (
        "Task complete. I processed the input and produced a structured result "
        "ready for the next step in the pipeline."
    )


class MockClient(ModelClient):
    provider = "mock"

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        text = _canned_response(messages)
        words = text.split(" ")
        emitted = ""
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            emitted += chunk
            await asyncio.sleep(0.02)  # simulate token streaming for the live view
            yield chunk

        prompt_tokens = sum(estimate_tokens(m.content) for m in messages)
        completion_tokens = estimate_tokens(emitted)
        self.last_usage = Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=estimate_cost(model, prompt_tokens, completion_tokens),
        )
