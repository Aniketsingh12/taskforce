"""Scheduled triggers.

A lightweight in-process scheduler: every tick it checks each workflow whose
`trigger_type == "schedule"` and fires a run when its cron expression matches
the current minute. Dependency-free; for multi-instance deployments this moves
to Celery beat (see docker-compose).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..core.config import settings
from ..db.store import store
from .cron import cron_matches


class Scheduler:
    def __init__(self, trigger_run) -> None:
        # trigger_run(workflow_id, input, source) -> run_id
        self._trigger_run = trigger_run
        self._task: asyncio.Task | None = None
        self._last_fired: dict[str, str] = {}  # workflow_id -> "YYYY-MM-DDTHH:MM"

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def check_due(self, now: datetime) -> list[str]:
        """Return ids of scheduled workflows due at `now` (minute-deduped)."""
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        due: list[str] = []
        for wf in store.list_workflows():
            if wf.trigger_type != "schedule" or not wf.schedule:
                continue
            if self._last_fired.get(wf.id) == minute_key:
                continue
            try:
                if cron_matches(wf.schedule, now):
                    self._last_fired[wf.id] = minute_key
                    due.append(wf.id)
            except ValueError:
                continue  # ignore malformed cron expressions
        return due

    async def _loop(self) -> None:
        while True:
            now = datetime.now(timezone.utc)
            for wf_id in self.check_due(now):
                # A single bad trigger (e.g. the workflow was deleted between
                # check_due and here, which raises 404) must not take down the
                # scheduler and with it every other scheduled run.
                try:
                    self._trigger_run(wf_id, "", "schedule")
                except Exception:  # noqa: BLE001 - isolate one workflow's failure
                    continue
            await asyncio.sleep(settings.scheduler_tick_seconds)
