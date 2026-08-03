// Visual pipeline of agents. Agents sharing a parallel_group stack in one
// column (they run concurrently); sequential agents are their own column.
// Highlights the active agent during a live run.
// (For the full version this is where React Flow drops in; the custom layout
// here is dependency-free and renders the same node/edge model.)

// Per-status border/colour. "running" also gets the pulsing ring (see index.css).
const STATUS_STYLES = {
  queued: "border-edge text-gray-400",
  running: "border-accent text-white agent-active",
  retrying: "border-amber-500 text-amber-200 agent-active",
  done: "border-emerald-500 text-emerald-200",
  failed: "border-red-500 text-red-200",
  skipped: "border-edge text-gray-600 opacity-50 line-through",
};

// Turn a flat, ordered agent list into columns. Consecutive agents that share a
// parallel_group collapse into one column rendered as a vertical stack.
function buildColumns(agents) {
  const columns = [];
  const groupCol = {}; // parallel_group → index of its column in `columns`
  for (const a of agents) {
    if (a.parallel_group != null) {
      if (groupCol[a.parallel_group] == null) {
        // First agent of this group → start a new parallel column.
        groupCol[a.parallel_group] = columns.length;
        columns.push({ parallel: true, agents: [a] });
      } else {
        // Subsequent group members join the existing column.
        columns[groupCol[a.parallel_group]].agents.push(a);
      }
    } else {
      // No group → its own sequential column.
      columns.push({ parallel: false, agents: [a] });
    }
  }
  return columns;
}

// A single agent node (role, model, current status).
function Node({ agent, status }) {
  return (
    <div
      className={`min-w-[150px] rounded-xl border bg-panel px-3 py-2 transition ${
        STATUS_STYLES[status] || STATUS_STYLES.queued
      }`}
    >
      <div className="text-sm font-semibold">{agent.role}</div>
      <div className="text-[11px] text-gray-400">{agent.model}</div>
      <div className="mt-1 text-[10px] uppercase tracking-wide opacity-70">{status}</div>
    </div>
  );
}

export default function PipelineGraph({ agents = [], statuses = {} }) {
  const columns = buildColumns(agents);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {columns.map((col, i) => (
        <div key={i} className="flex items-center gap-2">
          {col.parallel ? (
            // Parallel group: dashed box stacking the concurrent agents.
            <div className="flex flex-col gap-2 rounded-xl border border-dashed border-edge p-2">
              <span className="text-[10px] uppercase tracking-wide text-gray-500">parallel</span>
              {col.agents.map((a) => (
                <Node key={a.id} agent={a} status={statuses[a.id] || "queued"} />
              ))}
            </div>
          ) : (
            <Node agent={col.agents[0]} status={statuses[col.agents[0].id] || "queued"} />
          )}
          {/* Arrow between columns (not after the last). */}
          {i < columns.length - 1 && <span className="text-edge text-xl">→</span>}
        </div>
      ))}
    </div>
  );
}
