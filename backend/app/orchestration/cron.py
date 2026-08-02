"""Minimal 5-field cron matcher (dependency-free).

Fields: minute hour day-of-month month day-of-week
Supports: '*', lists 'a,b', ranges 'a-b', steps '*/n' and 'a-b/n'.
Enough for scheduled workflow triggers without pulling in croniter.
"""

from __future__ import annotations

from datetime import datetime

# Valid (low, high) bounds for each of the five cron fields, in order.
_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]  # min,hour,dom,mon,dow


def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    """Expand one cron field into the concrete set of values it matches."""
    values: set[int] = set()
    for part in field.split(","):           # handle comma lists: "1,15,30"
        step = 1
        if "/" in part:                      # handle steps: "*/5" or "0-30/5"
            part, step_s = part.split("/")
            step = int(step_s)
        if part in ("*", ""):                # wildcard → the whole range
            start, end = lo, hi
        elif "-" in part:                    # range: "9-17"
            start_s, end_s = part.split("-")
            start, end = int(start_s), int(end_s)
        else:                                # single value: "30"
            start = end = int(part)
        values.update(range(start, end + 1, step))
    # Clamp to the field's legal bounds.
    return {v for v in values if lo <= v <= hi}


def cron_matches(expr: str, now: datetime) -> bool:
    """True if `now` (minute resolution) satisfies the cron expression."""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"Cron must have 5 fields, got {len(fields)!r}")

    # Parse each field against its allowed range.
    minute, hour, dom, month, dow = (
        _parse_field(f, lo, hi) for f, (lo, hi) in zip(fields, _RANGES)
    )
    # Python's weekday() is Mon=0..Sun=6; cron uses Sun=0..Sat=6. Convert.
    now_dow = (now.weekday() + 1) % 7
    return (
        now.minute in minute
        and now.hour in hour
        and now.day in dom
        and now.month in month
        and now_dow in dow
    )
