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

    def __init__(self, name: str, description: str, fn: ToolFn, stage: str = "pre") -> None:
        self.name = name
        self.description = description
        self.fn = fn
        self.stage = stage

    def meta(self) -> dict:
        return {"name": self.name, "description": self.description, "stage": self.stage}


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "web_search": ToolSpec(
        "web_search", "Search the web for current information.", web_search, stage="pre"
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
