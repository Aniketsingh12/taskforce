"""Workflow CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response

from ..db.schema import WorkflowConfig
from ..db.store import store

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowConfig])
def list_workflows() -> list[WorkflowConfig]:
    return store.list_workflows()


@router.get("/{workflow_id}", response_model=WorkflowConfig)
def get_workflow(workflow_id: str) -> WorkflowConfig:
    wf = store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.post("", response_model=WorkflowConfig, status_code=201)
def create_workflow(workflow: WorkflowConfig) -> WorkflowConfig:
    """Create a workflow under a server-generated id.

    The id is always minted here — never taken from the request — so a POST can
    only ever insert. Honouring a client-supplied id would let a create silently
    overwrite an existing workflow (or a seeded template), because the store
    upserts. Use PUT /{id} to update.
    """
    workflow.id = uuid4().hex
    workflow.is_template = False  # templates are seeded, not client-created
    return store.save_workflow(workflow)


@router.post("/{workflow_id}/clone", response_model=WorkflowConfig, status_code=201)
def clone_workflow(workflow_id: str) -> WorkflowConfig:
    """Duplicate a workflow (e.g. a template) into a fresh editable copy."""
    src = store.get_workflow(workflow_id)
    if src is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    clone = src.model_copy(deep=True)
    clone.id = uuid4().hex
    clone.name = f"{src.name} (copy)"
    clone.is_template = False
    clone.created_at = datetime.now(timezone.utc)
    for agent in clone.agents:
        agent.id = uuid4().hex  # fresh agent ids
    return store.save_workflow(clone)


@router.put("/{workflow_id}", response_model=WorkflowConfig)
def update_workflow(workflow_id: str, workflow: WorkflowConfig) -> WorkflowConfig:
    if store.get_workflow(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    workflow.id = workflow_id
    return store.save_workflow(workflow)


@router.delete("/{workflow_id}", status_code=204, response_class=Response)
def delete_workflow(workflow_id: str) -> Response:
    if not store.delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return Response(status_code=204)
