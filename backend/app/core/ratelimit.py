"""In-process sliding-window rate limiter.

Deliberately dependency-free and in-memory, which matches how the rest of the
app is built (the scheduler and the WebSocket broker are in-process too).

Two honest caveats that come with that choice:
  * counters reset on redeploy/restart
  * it is per-process, so it does NOT hold across multiple replicas

Both are acceptable here because the rate limiter is a speed bump, not the
thing protecting your bill — the daily spend cap in `security.py` is. Moving to
Redis would fix both if this ever runs multi-replica.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """Allow at most `max_events` per `window_seconds` for each key."""

    def __init__(self, max_events: int, window_seconds: float) -> None:
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls_since_sweep = 0

    def allow(self, key: str) -> bool:
        """Record an attempt for `key`; True if it's within the limit."""
        if self.max_events <= 0:
            return True  # limiter disabled
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            # Drop timestamps that have aged out of the window.
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            self._calls_since_sweep += 1
            if self._calls_since_sweep >= 500:
                self._sweep(cutoff)

            if len(bucket) >= self.max_events:
                return False
            bucket.append(now)
            return True

    def _sweep(self, cutoff: float) -> None:
        """Drop keys with no recent activity so the dict can't grow forever.

        Amortised: runs every 500 calls rather than on each one, since an
        untrusted caller controls how many distinct keys (IPs) appear.
        Caller holds the lock.
        """
        self._calls_since_sweep = 0
        stale = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
        for k in stale:
            del self._hits[k]

    def reset(self) -> None:
        """Clear all counters (used by tests)."""
        with self._lock:
            self._hits.clear()
            self._calls_since_sweep = 0
