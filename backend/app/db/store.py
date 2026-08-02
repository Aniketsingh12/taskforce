"""Persistence layer.

SQLite-backed, storing each workflow/run as a JSON blob keyed by id. This keeps
the schema migration-free while giving real persistence across restarts, and it
runs with zero setup (stdlib `sqlite3`). The public interface matches what the
API and orchestrator use, so swapping in Supabase/Postgres later is a drop-in.

`store` is a module-level facade whose backend is created lazily from settings,
so tests can point `DB_PATH` at a temp file (or ":memory:") before import.
"""

from __future__ import annotations

import json
import sqlite3
import threading

from ..core.config import get_settings
from .schema import Run, WorkflowConfig


class SqliteStore:
    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        # check_same_thread=False: FastAPI may touch this from threadpool + loop.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT,
                started_at TEXT,
                data TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    # --- Workflows ---
    def save_workflow(self, wf: WorkflowConfig) -> WorkflowConfig:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO workflows (id, data) VALUES (?, ?)",
                (wf.id, wf.model_dump_json()),
            )
            self._conn.commit()
        return wf

    def get_workflow(self, workflow_id: str) -> WorkflowConfig | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM workflows WHERE id = ?", (workflow_id,)
            ).fetchone()
        return WorkflowConfig.model_validate_json(row[0]) if row else None

    def list_workflows(self) -> list[WorkflowConfig]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM workflows").fetchall()
        wfs = [WorkflowConfig.model_validate_json(r[0]) for r in rows]
        return sorted(wfs, key=lambda w: w.created_at)

    def delete_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM workflows WHERE id = ?", (workflow_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    # --- Runs ---
    def save_run(self, run: Run) -> Run:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO runs (id, workflow_id, started_at, data) "
                "VALUES (?, ?, ?, ?)",
                (run.id, run.workflow_id, run.started_at.isoformat(), run.model_dump_json()),
            )
            self._conn.commit()
        return run

    def get_run(self, run_id: str) -> Run | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return Run.model_validate_json(row[0]) if row else None

    def list_runs(self, workflow_id: str | None = None) -> list[Run]:
        with self._lock:
            if workflow_id:
                rows = self._conn.execute(
                    "SELECT data FROM runs WHERE workflow_id = ? ORDER BY started_at DESC",
                    (workflow_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT data FROM runs ORDER BY started_at DESC"
                ).fetchall()
        return [Run.model_validate_json(r[0]) for r in rows]


class _StoreFacade:
    """Lazily builds the backend from settings; delegates everything to it."""

    def __init__(self) -> None:
        self._backend: SqliteStore | None = None

    @property
    def backend(self) -> SqliteStore:
        if self._backend is None:
            self._backend = SqliteStore(get_settings().db_path)
        return self._backend

    def __getattr__(self, name: str):
        return getattr(self.backend, name)


store = _StoreFacade()
