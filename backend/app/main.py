"""TaskForce API entry point.

Wires routers, CORS, seeds the built-in templates, and starts the in-process
scheduler so scheduled workflows fire automatically.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
