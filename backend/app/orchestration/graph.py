"""Compile a node/edge graph into the engine's execution stages.

The visual builder lets you wire agents together freely. The engine, though,
runs ordered **stages** (`order` + `parallel_group`) — so a graph has to be
reduced to that form.

The reduction is a topological depth: an agent runs as early as its slowest
dependency allows. Everything sharing a depth has no path between it, so it can
run concurrently — which is exactly what a `parallel_group` means.

    A → B → D          depth 0: A          → stage 1
      ↘ C ↗            depth 1: B, C       → stage 2 (parallel)
                       depth 2: D          → stage 3

Agents with no incoming edge start at depth 0, so several roots run in parallel.
"""

from __future__ import annotations

from collections import defaultdict

from ..db.schema import AgentConfig, GraphEdge


def compute_depths(agents: list[AgentConfig], edges: list[GraphEdge]) -> dict[str, int]:
    """Longest-path depth per agent. Raises ValueError on a cycle."""
    ids = {a.id for a in agents}
    # Ignore edges pointing at agents that no longer exist (deleted nodes).
    live = [e for e in edges if e.source in ids and e.target in ids]

    incoming: dict[str, int] = {a.id: 0 for a in agents}
    children: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for e in live:
        if (e.source, e.target) in seen:
            continue  # tolerate duplicate edges from the UI
        seen.add((e.source, e.target))
        children[e.source].append(e.target)
        incoming[e.target] += 1

    # Kahn's algorithm, tracking the longest path rather than any path so a node
    # never runs before a slower branch it depends on.
    depth = {a.id: 0 for a in agents}
    queue = [aid for aid, n in incoming.items() if n == 0]
    processed = 0
    while queue:
        node = queue.pop(0)
        processed += 1
        for child in children[node]:
            depth[child] = max(depth[child], depth[node] + 1)
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)

    if processed != len(agents):
        raise ValueError(
            "The workflow graph contains a cycle — agents must flow forward."
        )
    return depth


def compile_graph(agents: list[AgentConfig], edges: list[GraphEdge]) -> list[AgentConfig]:
    """Set `order` and `parallel_group` on each agent from the graph shape.

    Mutates and returns the agents. A depth holding more than one agent becomes
    a parallel group; a depth with a single agent stays sequential.
    """
    if not edges:
        return agents  # list-built workflow — its explicit order already stands

    depth = compute_depths(agents, edges)
    at_depth: dict[int, list[AgentConfig]] = defaultdict(list)
    for agent in agents:
        at_depth[depth[agent.id]].append(agent)

    for level, group in at_depth.items():
        for agent in group:
            agent.order = level
            agent.parallel_group = level if len(group) > 1 else None
    return agents


def derive_edges(agents: list[AgentConfig]) -> list[GraphEdge]:
    """Infer edges for a workflow built as a list, so it can be shown as a graph.

    Consecutive stages are chained; every agent in a parallel stage links from
    each agent of the previous stage.
    """
    stages: dict[tuple, list[AgentConfig]] = defaultdict(list)
    for a in sorted(agents, key=lambda x: x.order):
        key = ("group", a.parallel_group) if a.parallel_group is not None else ("solo", a.id)
        stages[key].append(a)

    ordered = sorted(stages.values(), key=lambda g: min(a.order for a in g))
    edges: list[GraphEdge] = []
    for prev, nxt in zip(ordered, ordered[1:]):
        for p in prev:
            for n in nxt:
                edges.append(GraphEdge(source=p.id, target=n.id))
    return edges
