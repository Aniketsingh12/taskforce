"""Workflow CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response

from ..core.security import require_admin
from ..db.schema import WorkflowConfig
from ..db.store import store
from ..orchestration.graph import compile_graph, derive_edges

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

# Reading is public (that's the demo); anything that CHANGES stored data needs
# the admin token, so a visitor can't create clutter or delete your workflows.
# No-op when ADMIN_TOKEN is unset — see core/security.py.
_admin_only = [Depends(require_admin)]


def _apply_graph(workflow: WorkflowConfig) -> None:
    """Derive execution order from the visual graph, if one was supplied.

    Keeps a single source of truth: the canvas defines what runs when, and the
    engine's stage model is computed from it rather than maintained by hand.
    """
    try:
        compile_graph(workflow.agents, workflow.edges)
    except ValueError as exc:  # a cycle — reject rather than run something wrong
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[WorkflowConfig])
def list_workflows() -> list[WorkflowConfig]:
    return store.list_workflows()


@router.get("/{workflow_id}", response_model=WorkflowConfig)
def get_workflow(workflow_id: str) -> WorkflowConfig:
    wf = store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.post("", response_model=WorkflowConfig, status_code=201,
             dependencies=_admin_only)
def create_workflow(workflow: WorkflowConfig) -> WorkflowConfig:
    """Create a workflow under a server-generated id.

    The id is always minted here — never taken from the request — so a POST can
    only ever insert. Honouring a client-supplied id would let a create silently
    overwrite an existing workflow (or a seeded template), because the store
    upserts. Use PUT /{id} to update.
    """
    workflow.id = uuid4().hex
    workflow.is_template = False  # templates are seeded, not client-created
    _apply_graph(workflow)
    return store.save_workflow(workflow)


@router.get("/{workflow_id}/graph")
def workflow_graph(workflow_id: str) -> dict:
    """Nodes + edges for the visual builder.

    Workflows built as a list have no stored edges, so a chain is inferred from
    their stages — they open on the canvas already wired.
    """
    wf = store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    edges = wf.edges or derive_edges(wf.agents)
    return {
        "agents": [a.model_dump(mode="json") for a in wf.agents],
        "edges": [e.model_dump() for e in edges],
        "inferred": not wf.edges,
    }


@router.post("/{workflow_id}/clone", response_model=WorkflowConfig, status_code=201,
             dependencies=_admin_only)
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


@router.put("/{workflow_id}", response_model=WorkflowConfig, dependencies=_admin_only)
def update_workflow(workflow_id: str, workflow: WorkflowConfig) -> WorkflowConfig:
    if store.get_workflow(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    workflow.id = workflow_id
    _apply_graph(workflow)
    return store.save_workflow(workflow)


@router.delete("/{workflow_id}", status_code=204, response_class=Response,
               dependencies=_admin_only)
def delete_workflow(workflow_id: str) -> Response:
    if not store.delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return Response(status_code=204)
