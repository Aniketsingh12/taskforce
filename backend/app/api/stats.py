"""Aggregate observability — powers the cost/observability dashboard.

Surfaces success rate, total cost/tokens, the local-vs-API cost split (showing
the savings from local routing), and average run latency.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..db.schema import RunStatus
from ..db.store import store

router = APIRouter(prefix="/api", tags=["stats"])


def _is_local_model(model_used: str) -> bool:
    return model_used.startswith(("ollama", "mock"))


@router.get("/stats")
def stats() -> dict:
    runs = store.list_runs()
    total = len(runs)
    done = [r for r in runs if r.status == RunStatus.done]
    failed = [r for r in runs if r.status == RunStatus.failed]

    local_cost = api_cost = 0.0
    local_agents = api_agents = 0
    skipped_agents = 0
    latencies: list[int] = []
    for r in runs:
        for t in r.traces:
            # A skipped agent never ran, so it has no model and belongs in
            # neither column — counting it would skew the local-vs-API split.
            if t.status == RunStatus.skipped or not t.model_used:
                skipped_agents += 1
                continue
            if _is_local_model(t.model_used):
                local_cost += t.cost_usd
                local_agents += 1
            else:
                api_cost += t.cost_usd
                api_agents += 1
            if t.latency_ms:
                latencies.append(t.latency_ms)

    total_cost = round(sum(r.total_cost for r in runs), 6)
    return {
        "total_runs": total,
        "completed": len(done),
        "failed": len(failed),
        "success_rate": round(len(done) / total, 3) if total else 0.0,
        "total_cost": total_cost,
        "total_tokens": sum(r.total_tokens for r in runs),
        "cost_breakdown": {
            "local": round(local_cost, 6),
            "api": round(api_cost, 6),
            "local_agents": local_agents,
            "api_agents": api_agents,
            "skipped_agents": skipped_agents,
        },
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
    }
