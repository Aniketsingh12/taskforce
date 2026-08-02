"""File tool — write a run's deliverable to disk.

Writes into a sandboxed `outputs/` directory under the backend. In the full
version this is backed by an MCP file-ops server with proper scoping.
"""

from __future__ import annotations

import re
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs"


async def save_file(content: str, filename: str = "deliverable.md") -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "deliverable.md"
    path = OUTPUT_DIR / safe
    path.write_text(content, encoding="utf-8")
    return f"Saved deliverable to {path}"
