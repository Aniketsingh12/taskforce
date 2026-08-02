"""Domain models (conceptual schema from section 7).

These Pydantic models are the in-memory shapes used across the API and
orchestrator. In production they map 1:1 onto Supabase/Postgres tables
(workflows, agents, runs, traces, model_configs) — see `store.py` for the
swap-in point.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


OutputFormat = Literal["text", "json", "markdown"]
TriggerType = Literal["manual", "schedule", "webhook"]


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"
    skipped = "skipped"  # a conditional agent whose condition was not met


class AgentConfig(BaseModel):
    id: str = Field(default_factory=_uuid)
    role: str
    instructions: str
    model_provider: str = "mock"            # mock | ollama | openrouter
    model_name: str = "mock-default"
    # Optional per-agent fallback as "provider:model" (e.g.
    # "openrouter:openai/gpt-4o-mini"). Overrides the global fallback chain when
    # this agent's primary model fails. Empty = use the global default.
    fallback_model: str | None = None
    tools: list[str] = Field(default_factory=list)
    output_format: OutputFormat = "markdown"
    order: int = 0
    parallel_group: int | None = None       # agents sharing a group run together
    # Optional run condition: this agent runs only if the phrase appears in any
    # prior agent's output (prefix with "!" to invert). Empty = always run.
    condition: str | None = None


class WorkflowConfig(BaseModel):
    id: str = Field(default_factory=_uuid)
    name: str
    description: str = ""
    trigger_type: TriggerType = "manual"
    schedule: str | None = None              # cron expression for scheduled runs
    cost_cap: float | None = None
    is_template: bool = False                # seeded, cloneable starting points
    agents: list[AgentConfig] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class Trace(BaseModel):
    id: str = Field(default_factory=_uuid)
    run_id: str
    agent_id: str
    agent_role: str
    input: str = ""
    output: str = ""
    tools_called: list[str] = Field(default_factory=list)
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    status: RunStatus = RunStatus.queued


class Run(BaseModel):
    id: str = Field(default_factory=_uuid)
    workflow_id: str
    workflow_name: str = ""
    status: RunStatus = RunStatus.queued
    trigger_source: str = "manual"
    input: str = ""
    final_output: str = ""
    total_cost: float = 0.0
    total_tokens: int = 0
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
    traces: list[Trace] = Field(default_factory=list)
    error: str | None = None
