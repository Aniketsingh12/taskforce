import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { startRunStream } from "../lib/ws.js";
import PipelineGraph from "../components/PipelineGraph.jsx";
import LiveTrace from "../components/LiveTrace.jsx";
import CostBadge from "../components/CostBadge.jsx";

// The live run screen. It opens a WebSocket, then translates the backend's
// event stream into React state that drives the pipeline graph and the
// token-by-token output panels.
export default function RunView() {
  const { workflowId } = useParams();
  const [workflow, setWorkflow] = useState(null);
  const [input, setInput] = useState("The rise of multi-agent AI systems");
  const [running, setRunning] = useState(false);

  // --- Live run state, keyed by agent id ---
  const [agents, setAgents] = useState([]);       // agent list from run_started
  const [statuses, setStatuses] = useState({});   // id → queued|running|done|skipped
  const [outputs, setOutputs] = useState({});     // id → accumulated streamed text
  const [traces, setTraces] = useState({});       // id → finished Trace object
  const [toolCalls, setToolCalls] = useState({}); // id → [{tool, arguments}] the model chose
  const [activeId, setActiveId] = useState(null); // currently streaming agent
  const [finalRun, setFinalRun] = useState(null); // the completed Run
  const wsRef = useRef(null);                      // hold the socket to close on unmount

  // Load the workflow definition (so we can draw the pipeline before running)
  // and make sure the socket is closed if the user navigates away.
  useEffect(() => {
    api.getWorkflow(workflowId).then(setWorkflow).catch(() => {});
    return () => wsRef.current?.close();
  }, [workflowId]);

  // Running totals across all finished agents, recomputed when traces change.
  const totals = useMemo(() => {
    const list = Object.values(traces);
    return {
      cost: list.reduce((s, t) => s + (t.cost_usd || 0), 0),
      tokens: list.reduce((s, t) => s + (t.prompt_tokens || 0) + (t.completion_tokens || 0), 0),
    };
  }, [traces]);

  function start() {
    // Reset all live state for a fresh run.
    setRunning(true);
    setStatuses({});
    setOutputs({});
    setTraces({});
    setToolCalls({});
    setFinalRun(null);
    setActiveId(null);

    // Open the socket; every backend event flows through onEvent below.
    wsRef.current = startRunStream({
      workflowId,
      input,
      onClose: () => setRunning(false),
      onEvent: (ev) => {
        // This switch IS the live UI — each event type maps to a state update.
        switch (ev.type) {
          case "run_started":
            // Seed the agent list and mark them all queued.
            setAgents(ev.agents);
            setStatuses(Object.fromEntries(ev.agents.map((a) => [a.id, "queued"])));
            break;
          case "agent_started":
            // Light up the node and remember which agent is streaming.
            setActiveId(ev.agent_id);
            setStatuses((s) => ({ ...s, [ev.agent_id]: "running" }));
            break;
          case "token":
            // Append the new chunk to that agent's growing output.
            setOutputs((o) => ({ ...o, [ev.agent_id]: (o[ev.agent_id] || "") + ev.text }));
            break;
          case "agent_completed":
            // Store the finished trace (tokens/cost/latency) and mark done.
            setTraces((t) => ({ ...t, [ev.trace.agent_id]: ev.trace }));
            setStatuses((s) => ({ ...s, [ev.trace.agent_id]: "done" }));
            break;
          case "agent_skipped":
            // A conditional agent whose condition wasn't met.
            setStatuses((s) => ({ ...s, [ev.agent_id]: "skipped" }));
            break;
          case "tool_call":
            // The model chose to call a tool. Kept as its own state rather than
            // spliced into the output text, which gets replaced by the
            // authoritative trace once the agent finishes.
            setToolCalls((tc) => ({
              ...tc,
              [ev.agent_id]: [...(tc[ev.agent_id] || []), { tool: ev.tool, arguments: ev.arguments }],
            }));
            break;
          case "agent_retry":
            // The attempt failed/timed out and is restarting from scratch —
            // drop the partial text so it doesn't prepend the real answer.
            setOutputs((o) => ({ ...o, [ev.agent_id]: "" }));
            setStatuses((s) => ({ ...s, [ev.agent_id]: "retrying" }));
            break;
          case "run_completed":
            // Capture the final deliverable and stop.
            setFinalRun(ev.run);
            setActiveId(null);
            setRunning(false);
            break;
          case "run_failed":
            setRunning(false);
            setActiveId(null);
            break;
          default:
            break;
        }
      },
    });
  }

  // Before a run begins we draw the pipeline from the saved workflow; once a run
  // starts we use the agent list the backend sent (which carries live ids).
  const displayAgents =
    agents.length > 0
      ? agents
      : (workflow?.agents || [])
          .slice()
          .sort((a, b) => a.order - b.order)
          .map((a) => ({
            id: a.id,
            role: a.role,
            model: `${a.model_provider}:${a.model_name}`,
            parallel_group: a.parallel_group,
          }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{workflow?.name || "Run"}</h1>
          <p className="text-sm text-gray-400">{workflow?.description}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Live-updating cost/token total for the run. */}
          <CostBadge cost={totals.cost} tokens={totals.tokens} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Workflow input / goal…"
          className="flex-1 rounded-lg border border-edge bg-panel px-3 py-2 text-sm outline-none focus:border-accent"
        />
        <button
          onClick={start}
          disabled={running}
          className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {running ? "Running…" : "▶ Run live"}
        </button>
      </div>

      {/* The pipeline graph: nodes light up as their status changes. */}
      <div className="rounded-2xl border border-edge bg-ink/40 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
          Pipeline
        </h2>
        <PipelineGraph agents={displayAgents} statuses={statuses} />
      </div>

      {/* One streaming output panel per agent. */}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
          Live output
        </h2>
        <LiveTrace agents={displayAgents} outputs={outputs} traces={traces}
                   toolCalls={toolCalls} activeId={activeId} />
      </div>

      {/* The final deliverable, shown once the run completes. */}
      {finalRun && (
        <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5">
          <h2 className="mb-2 font-semibold text-emerald-200">Final deliverable</h2>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-sm text-gray-100">
            {finalRun.final_output}
          </pre>
        </div>
      )}
    </div>
  );
}
