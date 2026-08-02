"""Test fixtures: point the store at a throwaway SQLite file before app import."""

import os
import tempfile

# Must run before any `app.*` import so the cached settings pick it up.
_tmp = tempfile.NamedTemporaryFile(prefix="taskforce_test_", suffix=".db", delete=False)
_tmp.close()
os.environ["DB_PATH"] = _tmp.name
