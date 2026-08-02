"""Shared model-layer types and the abstract client interface."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class StreamResult:
    """Caller-owned sink for a stream's outcome.

    Passed into `ModelRouter.stream`; populated with the usage and the model
    that actually ran once the stream finishes. Being per-call, it keeps
    concurrent agents from sharing usage state on the shared router.
    """

    usage: Usage = field(default_factory=Usage)
    model: str = ""


# Rough per-1M-token prices (USD) for cost estimation in traces.
# Local models are $0. Hosted prices are approximate and easy to update.
PRICE_TABLE: dict[str, tuple[float, float]] = {  # model -> (in, out) per 1M tokens
    "mock-default": (0.0, 0.0),
    "anthropic/claude-3.5-haiku": (0.80, 4.0),
    "anthropic/claude-3.5-sonnet": (3.0, 15.0),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.5, 10.0),
    "google/gemini-flash-1.5": (0.075, 0.30),
    "meta-llama/llama-3.1-8b-instruct": (0.05, 0.05),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price_in, price_out = PRICE_TABLE.get(model, (0.0, 0.0))
    return round(
        (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000, 6
    )


def estimate_tokens(text: str) -> int:
    """Cheap heuristic (~4 chars/token) used when a provider omits usage."""
    return max(1, len(text) // 4)


class ModelClient(abc.ABC):
    """Every provider client implements a streaming chat call.

    `stream_chat` yields text chunks as they arrive, then sets `self.last_usage`
    so the orchestrator can record tokens/cost in the run trace.
    """

    provider: str = "base"

    def __init__(self) -> None:
        self.last_usage: Usage = Usage()

    @abc.abstractmethod
    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:  # pragma: no cover - interface
        ...
        yield ""  # pragma: no cover
