"""Persistence layer.

SQLite-backed. Each workflow/run is stored as a JSON blob (so the rich nested
Run object needs no schema migration), *plus* the fields we actually query —
status, timestamps, cost, and per-trace rows — as real indexed columns.

That split is deliberate: `get_run` stays a single cheap row read, while
`list_runs` and the stats dashboard become indexed queries and SQL aggregates
instead of "load every run and parse all of it in Python".

`store` is a module-level facade whose backend is created lazily from settings,
so tests can point `DB_PATH` at a temp file (or ":memory:") before import.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from ..core.config import get_settings
from .schema import Run, RunStatus, WorkflowConfig

# Columns added to `runs` after the original (id, workflow_id, started_at, data)
# schema shipped. Applied on open so an existing database upgrades in place.
_RUN_COLUMNS = {
    "workflow_name": "TEXT",
    "status": "TEXT",
    "trigger_source": "TEXT",
    "finished_at": "TEXT",
    "total_cost": "REAL",
    "total_tokens": "INTEGER",
}


class SqliteStore:
    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        # Create the parent directory if it doesn't exist yet — e.g. a fresh
        # Railway volume mounted at /data before its first write. sqlite3
        # itself won't create missing directories and would crash on boot.
        if path != ":memory:":
            parent = Path(path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
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
            -- Per-trace rows exist purely so observability is a SQL aggregate
            -- rather than a full scan + JSON parse of every run.
            CREATE TABLE IF NOT EXISTS traces (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                agent_role TEXT,
                model_used TEXT,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                status TEXT
            );
            """
        )
        self._migrate()
        self._conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_started    ON runs (started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_runs_workflow   ON runs (workflow_id, started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_runs_status     ON runs (status);
            CREATE INDEX IF NOT EXISTS idx_traces_run      ON traces (run_id);
            CREATE INDEX IF NOT EXISTS idx_traces_model    ON traces (model_used);
            """
        )
        self._conn.commit()

    # --- Schema upgrade -------------------------------------------------
    def _migrate(self) -> None:
        """Add any missing `runs` columns and backfill them from the JSON blob."""
        existing = {r[1] for r in self._conn.execute("PRAGMA table_info(runs)")}
        missing = [c for c in _RUN_COLUMNS if c not in existing]
        for col in missing:
            self._conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {_RUN_COLUMNS[col]}")
        if missing:
            # Backfill the new columns (and the traces table) from stored JSON.
            rows = self._conn.execute("SELECT data FROM runs").fetchall()
            for (blob,) in rows:
                try:
                    self._write_run_rows(Run.model_validate_json(blob))
                except Exception:  # noqa: BLE001 - skip unparseable legacy rows
                    continue
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
    def _write_run_rows(self, run: Run) -> None:
        """Upsert one run plus its trace rows. Caller holds the lock."""
        self._conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(id, workflow_id, started_at, data, workflow_name, status, "
            " trigger_source, finished_at, total_cost, total_tokens) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                run.id, run.workflow_id, run.started_at.isoformat(),
                run.model_dump_json(), run.workflow_name, run.status.value,
                run.trigger_source,
                run.finished_at.isoformat() if run.finished_at else None,
                run.total_cost, run.total_tokens,
            ),
        )
        # Traces are rewritten wholesale so they can never drift from the blob.
        self._conn.execute("DELETE FROM traces WHERE run_id = ?", (run.id,))
        self._conn.executemany(
            "INSERT OR REPLACE INTO traces "
            "(id, run_id, agent_role, model_used, prompt_tokens, "
            " completion_tokens, cost_usd, latency_ms, status) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (t.id, run.id, t.agent_role, t.model_used, t.prompt_tokens,
                 t.completion_tokens, t.cost_usd, t.latency_ms, t.status.value)
                for t in run.traces
            ],
        )

    def save_run(self, run: Run) -> Run:
        with self._lock:
            self._write_run_rows(run)
            self._conn.commit()
        return run

    def get_run(self, run_id: str) -> Run | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return Run.model_validate_json(row[0]) if row else None

    def list_runs(
        self,
        workflow_id: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Run]:
        """Most recent runs first, paginated (indexed on started_at)."""
        with self._lock:
            if workflow_id:
                rows = self._conn.execute(
                    "SELECT data FROM runs WHERE workflow_id = ? "
                    "ORDER BY started_at DESC LIMIT ? OFFSET ?",
                    (workflow_id, limit, offset),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT data FROM runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [Run.model_validate_json(r[0]) for r in rows]

    def spend_since(self, iso_timestamp: str) -> float:
        """Total cost of runs started at or after `iso_timestamp`.

        Powers the daily spend circuit breaker. `started_at` is stored as an
        ISO-8601 UTC string, which sorts lexicographically in the same order as
        chronologically — so a plain string comparison is a correct (and
        index-backed) time filter here.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(total_cost), 0) FROM runs WHERE started_at >= ?",
                (iso_timestamp,),
            ).fetchone()
        return float(row[0] or 0.0)

    def count_runs(self, workflow_id: str | None = None) -> int:
        with self._lock:
            if workflow_id:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE workflow_id = ?", (workflow_id,)
                ).fetchone()[0]
            return self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    # --- Observability (pure SQL — no full scan, no JSON parsing) ---
    def stats(self) -> dict:
        with self._lock:
            total, completed, failed, cost, tokens = self._conn.execute(
                "SELECT COUNT(*), "
                "       COALESCE(SUM(status = 'done'), 0), "
                "       COALESCE(SUM(status = 'failed'), 0), "
                "       COALESCE(SUM(total_cost), 0), "
                "       COALESCE(SUM(total_tokens), 0) "
                "FROM runs"
            ).fetchone()

            # Local = free local/demo inference; skipped agents never ran and
            # belong to neither column.
            local_cost, local_agents, api_cost, api_agents, skipped, avg_latency = (
                self._conn.execute(
                    "SELECT "
                    " COALESCE(SUM(CASE WHEN is_local THEN cost_usd END), 0), "
                    " COALESCE(SUM(CASE WHEN is_local THEN 1 END), 0), "
                    " COALESCE(SUM(CASE WHEN NOT is_local AND NOT is_skipped THEN cost_usd END), 0), "
                    " COALESCE(SUM(CASE WHEN NOT is_local AND NOT is_skipped THEN 1 END), 0), "
                    " COALESCE(SUM(is_skipped), 0), "
                    " COALESCE(AVG(CASE WHEN latency_ms > 0 THEN latency_ms END), 0) "
                    "FROM (SELECT cost_usd, latency_ms, "
                    "  (status = 'skipped' OR model_used IS NULL OR model_used = '') AS is_skipped, "
                    "  (model_used LIKE 'ollama%' OR model_used LIKE 'mock%') AS is_local "
                    " FROM traces)"
                ).fetchone()
            )

        return {
            "total_runs": total,
            "completed": completed,
            "failed": failed,
            "success_rate": round(completed / total, 3) if total else 0.0,
            "total_cost": round(float(cost), 6),
            "total_tokens": int(tokens),
            "cost_breakdown": {
                # float() so an all-zero aggregate still serialises as 0.0, not 0.
                "local": round(float(local_cost), 6),
                "api": round(float(api_cost), 6),
                "local_agents": int(local_agents),
                "api_agents": int(api_agents),
                "skipped_agents": int(skipped),
            },
            "avg_latency_ms": round(float(avg_latency)),
        }

    # --- Crash recovery ---
    def reconcile_interrupted_runs(self) -> int:
        """Fail runs left mid-flight by a crash/restart.

        A run is persisted as `running` the moment it starts, so a process that
        dies mid-run leaves it that way forever. Called on startup; returns how
        many were reconciled.
        """
        stuck = [RunStatus.running.value, RunStatus.queued.value]
        with self._lock:
            rows = self._conn.execute(
                f"SELECT data FROM runs WHERE status IN ({','.join('?' * len(stuck))})",
                stuck,
            ).fetchall()
            for (blob,) in rows:
                run = Run.model_validate_json(blob)
                run.status = RunStatus.failed
                run.error = "Interrupted — the server stopped while this run was in progress."
                self._write_run_rows(run)
            self._conn.commit()
        return len(rows)


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
