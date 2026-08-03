import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

// ComfyUI-style canvas: drag agents around, wire them together, and the
// execution order falls out of the graph shape (see backend orchestration/
// graph.py — depth becomes the stage, agents sharing a depth run in parallel).

const STATUS_RING = {
  running: "ring-2 ring-accent",
  retrying: "ring-2 ring-amber-500",
  done: "ring-2 ring-emerald-500",
  skipped: "opacity-40",
  failed: "ring-2 ring-red-500",
};

function AgentNode({ data, selected }) {
  return (
    <div
      className={`min-w-[190px] rounded-xl border bg-panel px-3 py-2 text-left shadow-lg ${
        selected ? "border-accent" : "border-edge"
      } ${STATUS_RING[data.status] || ""}`}
    >
      {/* Left = input from upstream agents, right = output to downstream. */}
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !bg-accent" />
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-semibold text-gray-100">{data.role}</span>
        {data.stage != null && (
          <span className="rounded bg-ink px-1.5 text-[10px] text-gray-500">
            stage {data.stage + 1}
          </span>
        )}
      </div>
      <div className="mt-0.5 truncate font-mono text-[10px] text-gray-400">{data.model}</div>
      <div className="mt-1 flex flex-wrap gap-1">
        {(data.tools || []).map((t) => (
          <span key={t} className="rounded bg-ink px-1.5 py-0.5 text-[10px] text-sky-300">
            🔧 {t}
          </span>
        ))}
        {data.condition && (
          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">
            ? {data.condition}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!h-3 !w-3 !bg-accent" />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

// Fallback layout for agents that have never been positioned: lay them out by
// execution stage so the first canvas open already reads left-to-right.
function autoPosition(agent, index) {
  return {
    x: (agent.order ?? index) * 260,
    y: agent.parallel_group != null ? (index % 3) * 130 : 60,
  };
}

export default function GraphEditor({
  agents,
  edges: initialEdges,
  statuses = {},
  selectedId,
  onSelect,
  onChange,          // (agents, edges) => void — positions + wiring
  readOnly = false,
}) {
  const initialNodes = useMemo(
    () =>
      agents.map((a, i) => ({
        id: a.id,
        type: "agent",
        position:
          a.position_x != null && a.position_y != null
            ? { x: a.position_x, y: a.position_y }
            : autoPosition(a, i),
        data: {
          role: a.role,
          model: `${a.model_provider}:${a.model_name}`,
          tools: a.tools,
          condition: a.condition,
          stage: a.order,
          status: statuses[a.id],
        },
      })),
    // Rebuild only when the agent set changes; positions are owned by the canvas.
    [agents.map((a) => a.id).join(","), agents.map((a) => a.role).join(",")]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(
    initialEdges.map((e) => ({ ...e, id: `${e.source}->${e.target}`, animated: true }))
  );

  // The workflow (and its wiring) arrives asynchronously, and useNodesState /
  // useEdgesState only seed an INITIAL value. One effect re-syncs both, in that
  // order — an edge whose nodes aren't in the store yet is dropped, so nodes
  // must land first. Dragged positions are preserved via `positions`.
  const positions = useRef({});
  const agentSignature = agents
    .map((a) => `${a.id}:${a.role}:${a.model_provider}:${a.model_name}:${a.order}`)
    .join("|");
  const edgeSignature = initialEdges
    .map((e) => `${e.source}->${e.target}`)
    .sort()
    .join(",");

  useEffect(() => {
    setNodes((current) => {
      const byId = new Map(current.map((n) => [n.id, n]));
      for (const n of current) positions.current[n.id] = n.position;
      return agents.map((a, i) => {
        const data = {
          role: a.role,
          model: `${a.model_provider}:${a.model_name}`,
          tools: a.tools,
          condition: a.condition,
          stage: a.order,
          status: statuses[a.id],
        };
        const existing = byId.get(a.id);
        // Reuse the existing node object so React Flow's internal bookkeeping
        // (measured size, initialisation) survives. Rebuilding it from scratch
        // resets that, leaving nodes `visibility: hidden` and their edges
        // unrendered because endpoints can never be resolved.
        return existing
          ? { ...existing, data }
          : {
              id: a.id,
              type: "agent",
              position:
                positions.current[a.id] ||
                (a.position_x != null && a.position_y != null
                  ? { x: a.position_x, y: a.position_y }
                  : autoPosition(a, i)),
              data,
            };
      });
    });
    setEdges(
      initialEdges
        // Drop wiring that references an agent that no longer exists.
        .filter((e) => agents.some((a) => a.id === e.source) && agents.some((a) => a.id === e.target))
        .map((e) => ({ ...e, id: `${e.source}->${e.target}`, animated: true }))
    );
  }, [agentSignature, edgeSignature, setNodes, setEdges]); // eslint-disable-line react-hooks/exhaustive-deps

  // Status rings update every run event; keep them off the structural sync
  // above so a status change never rebuilds positions.
  //
  // Both the dependency and the returned array must be stable when nothing
  // changed: `statuses` is a fresh object on every parent render, and returning
  // a new array unconditionally would re-render forever — which stops React
  // Flow ever finishing measurement, leaving nodes hidden and edges unrendered.
  const statusSignature = agents.map((a) => `${a.id}:${statuses[a.id] ?? ""}`).join("|");
  useEffect(() => {
    setNodes((ns) => {
      let changed = false;
      const next = ns.map((n) => {
        const status = statuses[n.id];
        if (n.data.status === status) return n;
        changed = true;
        return { ...n, data: { ...n.data, status } };
      });
      return changed ? next : ns;
    });
  }, [statusSignature, setNodes]); // eslint-disable-line react-hooks/exhaustive-deps

  // Publish only in response to a real gesture — connect, drag, or delete.
  // Firing on every render would echo the canvas's initial empty state back to
  // the parent and wipe the wiring before it finishes loading.
  const publish = useCallback(
    (nextNodes, nextEdges) => {
      if (readOnly || !onChange) return;
      const positions = Object.fromEntries(nextNodes.map((n) => [n.id, n.position]));
      onChange(
        agents.map((a) => ({
          ...a,
          position_x: positions[a.id]?.x ?? a.position_x,
          position_y: positions[a.id]?.y ?? a.position_y,
        })),
        nextEdges.map((e) => ({ source: e.source, target: e.target }))
      );
    },
    [agents, onChange, readOnly]
  );

  const onConnect = useCallback(
    (params) =>
      setEdges((es) => {
        const next = addEdge(
          { ...params, id: `${params.source}->${params.target}`, animated: true }, es
        );
        publish(nodes, next);
        return next;
      }),
    [setEdges, publish, nodes]
  );

  const handleEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      if (changes.some((c) => c.type === "remove")) {
        setEdges((es) => {
          publish(nodes, es);
          return es;
        });
      }
    },
    [onEdgesChange, setEdges, publish, nodes]
  );

  // Applying selection inline in the JSX would hand React Flow brand-new node
  // objects on every render, resetting the measurement it needs before it will
  // draw edges. Only the node whose selection actually changed is replaced.
  const displayNodes = useMemo(
    () =>
      nodes.map((n) =>
        n.selected === (n.id === selectedId)
          ? n
          : { ...n, selected: n.id === selectedId }
      ),
    [nodes, selectedId]
  );

  return (
    <div className="h-[460px] overflow-hidden rounded-2xl border border-edge bg-ink/60">
      <ReactFlow
        nodes={displayNodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={readOnly ? undefined : onConnect}
        onNodeDragStop={() => publish(nodes, edges)}
        onNodeClick={(_, node) => onSelect?.(node.id)}
        nodeTypes={nodeTypes}
        nodesDraggable={!readOnly}
        edgesFocusable={!readOnly}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2a3142" gap={18} />
        <Controls className="!bg-panel !text-gray-900" />
        <MiniMap
          pannable
          className="!bg-panel"
          nodeColor={() => "#6366f1"}
          maskColor="rgba(10,12,18,0.7)"
        />
      </ReactFlow>
    </div>
  );
}
