"""Tool registry — name → callable, plus metadata for the UI's ToolPicker."""

from __future__ import annotations

from typing import Awaitable, Callable

from .file_tool import save_file
from .web_search import web_search

ToolFn = Callable[..., Awaitable[str]]


class ToolSpec:
    """A callable tool plus when it runs relative to the model call.

    `stage="pre"`  — runs before the model; receives the run input and its
                     result is injected into the prompt as context (web_search).
    `stage="post"` — runs after the model; receives the agent's own output, so
                     output sinks record the actual deliverable (save_file).
    """

    def __init__(
        self,
        name: str,
        description: str,
        fn: ToolFn,
        stage: str = "pre",
        parameters: dict | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.fn = fn
        self.stage = stage
        # JSON Schema for the arguments, sent to the model so it can call this
        # tool itself. Defaults to a single free-text `query`.
        self.parameters = parameters or {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Input for the tool."}},
            "required": ["query"],
        }

    def meta(self) -> dict:
        return {"name": self.name, "description": self.description, "stage": self.stage}

    def to_schema(self) -> dict:
        """OpenAI-style function schema (also accepted by Ollama)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "web_search": ToolSpec(
        "web_search", "Search the web for current information.", web_search, stage="pre",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
            },
            "required": ["query"],
        },
    ),
    # Post-stage: previously this ran before the model and saved the run INPUT,
    # so the deliverable file never contained the agent's actual output.
    "save_file": ToolSpec(
        "save_file", "Write this agent's output to a file.", save_file, stage="post"
    ),
}


def get_tool(name: str) -> ToolSpec | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[dict]:
    return [spec.meta() for spec in TOOL_REGISTRY.values()]
