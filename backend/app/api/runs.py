"""Run lifecycle: trigger, history, and live streaming over WebSocket."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..db.schema import Run
from ..db.store import store
from ..orchestration import Orchestrator
from ..ws import broker

router = APIRouter(prefix="/api/runs", tags=["runs"])
orchestrator = Orchestrator()

# asyncio only holds a weak reference to a bare create_task(...), so a run can be
# garbage-collected before it finishes. Keep a strong ref until the task is done.
_background_runs: set[asyncio.Task] = set()


def _spawn_run(workflow, run_input: str, run_id: str, trigger_source: str) -> None:
    task = asyncio.create_task(
        orchestrator.run_workflow(
            workflow,
            run_input,
            run_id=run_id,
            trigger_source=trigger_source,
            emit=broker.emitter(run_id),
        )
    )
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)


class TriggerRequest(BaseModel):
    workflow_id: str
    input: str = ""


class TriggerResponse(BaseModel):
    run_id: str


def start_run(workflow_id: str, run_input: str, trigger_source: str) -> str:
    """Create the background run task and return its id (call from the loop).

    Shared by the manual trigger, webhooks, and the scheduler.
    """
    workflow = store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    run_id = uuid.uuid4().hex
    _spawn_run(workflow, run_input, run_id, trigger_source)
    return run_id


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_run(req: TriggerRequest) -> TriggerResponse:
    """Start a run in the background. Subscribe to /api/runs/ws/{run_id} to watch."""
    run_id = start_run(req.workflow_id, req.input, "manual")
    return TriggerResponse(run_id=run_id)


@router.get("", response_model=list[Run])
def list_runs(workflow_id: str | None = None) -> list[Run]:
    return store.list_runs(workflow_id)


@router.get("/{run_id}", response_model=Run)
def get_run(run_id: str) -> Run:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.websocket("/ws/{run_id}")
async def stream_run(websocket: WebSocket, run_id: str) -> None:
    """Stream live events for a run that was started via /trigger."""
    await websocket.accept()
    try:
        async for event in broker.subscribe(run_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass


@router.websocket("/ws")
async def start_and_stream(websocket: WebSocket) -> None:
    """Start a run AND stream it over a single socket — the live-demo path.

    Client sends {"workflow_id": "...", "input": "..."} then receives the full
    event stream (run_started → tokens → run_completed).
    """
    await websocket.accept()
    try:
        req = await websocket.receive_json()
        workflow = store.get_workflow(req.get("workflow_id", ""))
        if workflow is None:
            await websocket.send_json({"type": "error", "message": "Workflow not found"})
            await websocket.close()
            return
        run_id = uuid.uuid4().hex
        _spawn_run(workflow, req.get("input", ""), run_id, "manual")
        async for event in broker.subscribe(run_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
