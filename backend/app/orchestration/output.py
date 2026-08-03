"""Structured-output extraction.

`output_format="json"` was previously advisory — it only added a sentence to the
prompt and nothing ever checked the result. Models rarely return bare JSON:
they wrap it in prose ("Here's the JSON:"), fence it in ```json blocks, or add a
trailing explanation. This module digs the JSON back out and reports honestly
when there isn't any.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ```json { ... } ```  or a plain ``` fenced block
_FENCE = re.compile(r"```(?:json|JSON)?\s*\n?(.+?)```", re.S)


def _balanced_slice(text: str) -> str | None:
    """Return the first complete {...} or [...] region in `text`.

    Scans with a depth counter (and string/escape awareness) so braces inside
    string literals don't end the object early.
    """
    start = None
    opener = closer = ""
    depth = 0
    in_string = False
    escaped = False

    for i, ch in enumerate(text):
        if start is None:
            if ch in "{[":
                start = i
                opener = ch
                closer = "}" if ch == "{" else "]"
                depth = 1
            continue

        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> tuple[Any | None, str | None]:
    """Best-effort parse of a model's JSON output.

    Returns `(value, None)` on success or `(None, reason)` when nothing
    parseable is present. Tries, in order: the whole string, any fenced code
    block, then the first balanced brace/bracket region.
    """
    if not text or not text.strip():
        return None, "empty output"

    candidates: list[str] = [text.strip()]
    candidates += [m.group(1).strip() for m in _FENCE.finditer(text)]
    if (sliced := _balanced_slice(text)) is not None:
        candidates.append(sliced)

    for candidate in candidates:
        try:
            return json.loads(candidate), None
        except json.JSONDecodeError:
            continue

    return None, "no valid JSON found in the model's output"


# Appended to the prompt when a JSON agent returns something unparseable, so the
# retry is a correction rather than an identical second attempt.
JSON_REPAIR_NUDGE = (
    "Your previous reply could not be parsed as JSON. Reply with ONLY a single "
    "valid JSON value — no prose, no explanation, no markdown code fences."
)
