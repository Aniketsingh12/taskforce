"""Live run event broker.

A tiny in-process pub/sub keyed by run_id. The orchestrator publishes events
(run_started, agent_started, token, agent_completed, run_completed/failed) and
WebSocket clients subscribe to stream them to the live pipeline view.

Subscription is index-based over a per-run buffer, so a client that connects
after a run starts replays everything from the beginning with no gaps or
duplicates — important for the "watch it run live" UX.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

# When one of these events is seen, the subscriber knows the run is over and
# can stop iterating.
_TERMINAL = {"run_completed", "run_failed"}

# How long a finished run's events stay replayable before being evicted. Long
# enough for a client to reconnect and replay; short enough that a long-lived
# server doesn't accumulate every event of every run forever.
_RETENTION_SECONDS = 600


class RunBroker:
    def __init__(self) -> None:
        # run_id → ordered list of every event published for that run. We keep
        # the whole history so late subscribers can replay it.
        self._buffers: dict[str, list[dict]] = {}
        # run_id → an asyncio.Event used to wake sleeping subscribers when a new
        # event is published.
        self._notifiers: dict[str, asyncio.Event] = {}
        # run_id → monotonic time the run finished, used to expire its buffer.
        self._finished_at: dict[str, float] = {}

    def _notifier(self, run_id: str) -> asyncio.Event:
        return self._notifiers.setdefault(run_id, asyncio.Event())

    def _evict_expired(self) -> None:
        """Drop buffers for runs that finished longer than the retention window
        ago. Called on publish, so cleanup costs nothing when idle."""
        if not self._finished_at:
            return
        cutoff = time.monotonic() - _RETENTION_SECONDS
        for run_id in [r for r, t in self._finished_at.items() if t < cutoff]:
            self._buffers.pop(run_id, None)
            self._notifiers.pop(run_id, None)
            self._finished_at.pop(run_id, None)

    async def publish(self, run_id: str, event: dict) -> None:
        # Append to the buffer, then wake anyone waiting on this run.
        self._buffers.setdefault(run_id, []).append(event)
        if event.get("type") in _TERMINAL:
            # Start this run's retention clock; its buffer is evicted later.
            self._finished_at[run_id] = time.monotonic()
        self._evict_expired()
        self._notifier(run_id).set()

    async def subscribe(self, run_id: str) -> AsyncIterator[dict]:
        # `idx` is how far this subscriber has read into the shared buffer.
        # Because we drive replay + live delivery from the SAME list by index,
        # there's no way to drop or double-deliver an event.
        idx = 0
        while True:
            buf = self._buffers.get(run_id, [])
            # Drain everything new since we last looked.
            while idx < len(buf):
                event = buf[idx]
                idx += 1
                yield event
                if event.get("type") in _TERMINAL:
                    return
            # Caught up — wait for the next publish.
            notifier = self._notifier(run_id)
            notifier.clear()
            # Guard against a publish that happened between the length check and
            # clear(): if more arrived, loop again instead of sleeping.
            if idx < len(self._buffers.get(run_id, [])):
                continue
            await notifier.wait()

    def emitter(self, run_id: str):
        """Return an async emit(event) bound to this run, for the orchestrator."""

        async def emit(event: dict) -> None:
            await self.publish(run_id, event)

        return emit


# Single shared broker for the whole process.
broker = RunBroker()
