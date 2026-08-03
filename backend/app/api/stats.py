"""Aggregate observability — powers the cost/observability dashboard.

Surfaces success rate, total cost/tokens, the local-vs-API cost split (showing
the savings from local routing), and average run latency.

The aggregation itself is SQL in the store, so this stays O(1) work here rather
than loading every run and walking every trace on each dashboard poll.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..db.store import store

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats() -> dict:
    return store.stats()
