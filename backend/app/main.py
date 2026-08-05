"""TaskForce API entry point.

Wires routers, CORS, seeds the built-in templates, and starts the in-process
scheduler so scheduled workflows fire automatically. Also serves the built
frontend (if present) so the whole app can run as a single deployed service —
see the STATIC_DIR block at the bottom.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import models as models_api
from .api import runs as runs_api
from .api import stats as stats_api
from .api import webhooks as webhooks_api
from .api import workflows as workflows_api
from .core.config import settings
from .db.store import store
from .orchestration import Scheduler, default_templates

scheduler = Scheduler(trigger_run=runs_api.start_run)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Re-seed the built-in templates on every boot so edits to templates.py
    # actually reach an existing database. Safe because templates are cloned
    # before editing — user workflows have their own ids and are never touched.
    for wf in default_templates():
        store.save_workflow(wf)
    # Runs are persisted as "running" the moment they start, so anything still
    # in that state at boot was killed mid-flight by a crash, restart, or a
    # reload. Close them out instead of leaving them running forever.
    if (recovered := store.reconcile_interrupted_runs()):
        print(f"[startup] marked {recovered} interrupted run(s) as failed")
    if settings.scheduler_enabled:
        scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workflows_api.router)
app.include_router(runs_api.router)
app.include_router(models_api.router)
app.include_router(stats_api.router)
app.include_router(webhooks_api.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}


# --- Serve the built frontend, if present (single-service deployment) ---
#
# The root Dockerfile builds the Vite app and copies its output here, one
# level up from this file's `app` package. Locally (no Docker) this directory
# never exists, so the block below is skipped entirely and the API-only dev
# workflow (`python run.py`, separate Vite dev server) is unaffected.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if STATIC_DIR.is_dir():
    # Vite's hashed JS/CSS bundle. Everything else (index.html, and any future
    # root-level file like a favicon) is handled by the catch-all below.
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        """Serve the SPA for any route the API didn't already claim.

        Registered LAST and after every `include_router` above, so a real API
        route always wins the match first — this only ever sees requests that
        those routers declined. An unmatched /api/* path still 404s as JSON
        rather than silently returning the HTML shell, which would be a
        confusing failure mode for API callers.
        """
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        # Anything else (a client-side route like /builder/abc) → let React
        # Router take over once the shell loads.
        return FileResponse(STATIC_DIR / "index.html")
