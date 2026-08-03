"""Shared model-layer types and the abstract client interface."""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class ToolCall:
    """A tool invocation the model asked for."""

    id: str
    name: str
    arguments: dict


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)  # assistant turns
    tool_call_id: str | None = None                           # tool results
    name: str | None = None                                   # tool result's tool


def to_openai_wire(m: ChatMessage) -> dict:
    """Serialise a message for an OpenAI-compatible API (OpenRouter)."""
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.content}
    msg: dict = {"role": m.role, "content": m.content}
    if m.tool_calls:
        # OpenAI takes arguments as a JSON *string*, not an object.
        msg["tool_calls"] = [
            {"id": c.id, "type": "function",
             "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
            for c in m.tool_calls
        ]
    return msg


def to_ollama_wire(m: ChatMessage) -> dict:
    """Serialise a message for Ollama's /api/chat.

    Same shape as OpenAI except tool-call arguments stay objects and tool
    results carry the tool's name rather than a call id.
    """
    if m.role == "tool":
        return {"role": "tool", "content": m.content, "name": m.name or ""}
    msg: dict = {"role": m.role, "content": m.content}
    if m.tool_calls:
        msg["tool_calls"] = [
            {"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls
        ]
    return msg


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
    # Tools the model asked to run this turn. Empty means it produced a final
    # answer and the ReAct loop can stop.
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Names of tools actually executed across the whole loop, for the trace.
    tools_called: list[str] = field(default_factory=list)


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
    # Clients that can do model-driven tool calling set this; the ReAct loop
    # falls back to staged tools for those that can't.
    supports_tools: bool = False

    def __init__(self) -> None:
        self.last_usage: Usage = Usage()
        # Populated when the model requests tools (see ToolCall).
        self.last_tool_calls: list[ToolCall] = []

    @abc.abstractmethod
    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:  # pragma: no cover - interface
        ...
        yield ""  # pragma: no cover
