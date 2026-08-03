"""Compiling a visual node graph down to the engine's execution stages."""

import asyncio

import pytest

from app.db.schema import AgentConfig, GraphEdge, RunStatus, WorkflowConfig
from app.orchestration import Orchestrator
from app.orchestration.graph import compile_graph, derive_edges


def _agents(*roles):
    return [AgentConfig(role=r, instructions=r) for r in roles]


def test_diamond_graph_becomes_a_parallel_stage():
    """A → (B, C) → D: the middle pair must run concurrently."""
    a, b, c, d = _agents("A", "B", "C", "D")
    edges = [
        GraphEdge(source=a.id, target=b.id),
        GraphEdge(source=a.id, target=c.id),
        GraphEdge(source=b.id, target=d.id),
        GraphEdge(source=c.id, target=d.id),
    ]
    compile_graph([a, b, c, d], edges)

    assert (a.order, a.parallel_group) == (0, None)
    assert b.order == c.order == 1
    assert b.parallel_group == c.parallel_group == 1  # same stage → concurrent
    assert (d.order, d.parallel_group) == (2, None)


def test_longest_path_wins_so_nothing_runs_early():
    """A→B→C plus A→C: C must wait for B, not run alongside it."""
    a, b, c = _agents("A", "B", "C")
    edges = [
        GraphEdge(source=a.id, target=b.id),
        GraphEdge(source=b.id, target=c.id),
        GraphEdge(source=a.id, target=c.id),  # shortcut edge
    ]
    compile_graph([a, b, c], edges)
    assert a.order == 0 and b.order == 1
    assert c.order == 2, "C depends on B, so it cannot share B's stage"


def test_multiple_roots_start_together():
    a, b, c = _agents("A", "B", "C")
    edges = [GraphEdge(source=a.id, target=c.id), GraphEdge(source=b.id, target=c.id)]
    compile_graph([a, b, c], edges)
    assert a.order == b.order == 0
    assert a.parallel_group == b.parallel_group == 0


def test_cycles_are_rejected():
    a, b = _agents("A", "B")
    edges = [GraphEdge(source=a.id, target=b.id), GraphEdge(source=b.id, target=a.id)]
    with pytest.raises(ValueError, match="cycle"):
        compile_graph([a, b], edges)


def test_edges_to_deleted_agents_are_ignored():
    a, b = _agents("A", "B")
    edges = [GraphEdge(source=a.id, target=b.id),
             GraphEdge(source="ghost-id", target=b.id)]
    compile_graph([a, b], edges)  # must not raise or hang
    assert b.order == 1


def test_no_edges_leaves_the_list_order_alone():
    a, b = _agents("A", "B")
    a.order, b.order = 5, 9
    compile_graph([a, b], [])
    assert (a.order, b.order) == (5, 9)


def test_derive_edges_chains_a_list_built_workflow():
    """List-built workflows open on the canvas already wired."""
    a, b, c, d = _agents("A", "B", "C", "D")
    a.order = 0
    b.order = c.order = 1
    b.parallel_group = c.parallel_group = 1
    d.order = 2

    edges = derive_edges([a, b, c, d])
    pairs = {(e.source, e.target) for e in edges}
    assert pairs == {
        (a.id, b.id), (a.id, c.id),   # fan out into the parallel stage
        (b.id, d.id), (c.id, d.id),   # fan back in
    }


def test_compiled_graph_actually_executes_in_that_shape():
    """End-to-end: what you wire is what the engine runs."""
    a, b, c, d = _agents("Planner", "Left", "Right", "Merger")
    wf = WorkflowConfig(
        id="test-graph-exec", name="Graph Exec", agents=[a, b, c, d],
        edges=[
            GraphEdge(source=a.id, target=b.id),
            GraphEdge(source=a.id, target=c.id),
            GraphEdge(source=b.id, target=d.id),
            GraphEdge(source=c.id, target=d.id),
        ],
    )
    compile_graph(wf.agents, wf.edges)
    run = asyncio.run(Orchestrator().run_workflow(wf, "go", emit=lambda e: None))

    assert run.status == RunStatus.done
    roles = [t.agent_role for t in run.traces]
    assert roles[0] == "Planner"
    assert roles[-1] == "Merger"
    assert set(roles[1:3]) == {"Left", "Right"}
