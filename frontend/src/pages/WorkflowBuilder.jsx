import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api.js";
import ModelPicker from "../components/ModelPicker.jsx";
import ToolPicker from "../components/ToolPicker.jsx";
import GraphEditor from "../components/GraphEditor.jsx";

const newAgent = () => ({
  role: "New Agent",
  instructions: "",
  model_provider: "mock",
  model_name: "mock-default",
  tools: [],
  output_format: "markdown",
  parallel_group: null,
  condition: null,
  tool_mode: "auto",
  max_retries: 1,
  timeout_seconds: 300,
});

// Agents need stable ids up front so the canvas can wire them before the first
// save (the server would otherwise assign them).
const uid = () =>
  (crypto.randomUUID?.() || Math.random().toString(36).slice(2)).replace(/-/g, "");

const blank = () => ({
  name: "Untitled workflow",
  description: "",
  trigger_type: "manual",
  schedule: "",
  cost_cap: null,
  agents: [{ ...newAgent(), id: uid() }],
  edges: [],
});

function AgentEditor({ agent, index, count, onChange, onMove, onRemove }) {
  // Pass `index` through, like onMove/onRemove do — the parent's setAgent is
  // (index, agent). Omitting it silently no-ops every edit in this panel.
  const set = (patch) => onChange(index, { ...agent, ...patch });
  return (
    <div className="rounded-xl border border-edge bg-panel p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent/20 text-xs text-accent">
          {index + 1}
        </span>
        <input
          value={agent.role}
          onChange={(e) => set({ role: e.target.value })}
          className="flex-1 rounded border border-edge bg-ink px-2 py-1 text-sm font-semibold outline-none focus:border-accent"
        />
        <button onClick={() => onMove(index, -1)} disabled={index === 0}
          className="rounded px-2 py-1 text-xs text-gray-400 hover:text-white disabled:opacity-30">↑</button>
        <button onClick={() => onMove(index, 1)} disabled={index === count - 1}
          className="rounded px-2 py-1 text-xs text-gray-400 hover:text-white disabled:opacity-30">↓</button>
        <button onClick={() => onRemove(index)}
          className="rounded px-2 py-1 text-xs text-red-300 hover:text-red-200">✕</button>
      </div>

      <textarea
        value={agent.instructions}
        onChange={(e) => set({ instructions: e.target.value })}
        placeholder="System instructions for this agent…"
        rows={2}
        className="mb-3 w-full rounded border border-edge bg-ink px-2 py-1.5 text-xs outline-none focus:border-accent"
      />

      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-[11px] text-gray-400">
          Model
          <div className="mt-1">
            <ModelPicker
              value={{ provider: agent.model_provider, model: agent.model_name }}
              onChange={(v) => set({ model_provider: v.provider, model_name: v.model })}
            />
          </div>
        </label>
        <label className="text-[11px] text-gray-400">
          Output format
          <select
            value={agent.output_format}
            onChange={(e) => set({ output_format: e.target.value })}
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-2 py-1.5 text-xs outline-none focus:border-accent"
          >
            <option value="markdown">markdown</option>
            <option value="text">text</option>
            <option value="json">json</option>
          </select>
        </label>
      </div>

      <div className="mt-3 text-[11px] text-gray-400">
        Tools
        <div className="mt-1">
          <ToolPicker value={agent.tools} onChange={(tools) => set({ tools })} />
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <label className="text-[11px] text-gray-400">
          Tool use
          <select
            value={agent.tool_mode ?? "auto"}
            onChange={(e) => set({ tool_mode: e.target.value })}
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-2 py-1.5 text-xs outline-none focus:border-accent"
          >
            <option value="auto">auto — model decides</option>
            <option value="staged">staged — always run</option>
          </select>
        </label>
        <label className="text-[11px] text-gray-400">
          Retries
          <input
            type="number"
            min="0"
            value={agent.max_retries ?? 1}
            onChange={(e) => set({ max_retries: Number(e.target.value) })}
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-2 py-1.5 text-xs outline-none focus:border-accent"
          />
        </label>
        <label className="text-[11px] text-gray-400">
          Timeout (s)
          <input
            type="number"
            min="1"
            value={agent.timeout_seconds ?? ""}
            placeholder="none"
            onChange={(e) =>
              set({ timeout_seconds: e.target.value === "" ? null : Number(e.target.value) })
            }
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-2 py-1.5 text-xs outline-none focus:border-accent"
          />
        </label>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <label className="text-[11px] text-gray-400">
          Parallel group <span className="text-gray-600">(same number = run together)</span>
          <input
            type="number"
            value={agent.parallel_group ?? ""}
            onChange={(e) => set({ parallel_group: e.target.value === "" ? null : Number(e.target.value) })}
            placeholder="none"
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-2 py-1.5 text-xs outline-none focus:border-accent"
          />
        </label>
        <label className="text-[11px] text-gray-400">
          Run condition <span className="text-gray-600">(phrase in prior output; ! to invert)</span>
          <input
            value={agent.condition ?? ""}
            onChange={(e) => set({ condition: e.target.value || null })}
            placeholder="always"
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-2 py-1.5 text-xs outline-none focus:border-accent"
          />
        </label>
      </div>
    </div>
  );
}

export default function WorkflowBuilder() {
  const { workflowId } = useParams();
  const navigate = useNavigate();
  const [wf, setWf] = useState(blank());
  const [saving, setSaving] = useState(false);
  const [view, setView] = useState("canvas"); // canvas | list
  const [selectedId, setSelectedId] = useState(null);
  const editing = Boolean(workflowId);

  useEffect(() => {
    if (workflowId) {
      // Pull the graph too: workflows built as a list have no stored edges, so
      // the server infers a chain from their stages and they open pre-wired.
      Promise.all([api.getWorkflow(workflowId), api.workflowGraph(workflowId)])
        .then(([w, g]) =>
          setWf({ ...w, schedule: w.schedule || "", edges: g.edges || [] })
        )
        .catch(() => {});
    } else {
      // No id in the URL → this is the "new workflow" screen. Reset explicitly
      // so a previously-loaded workflow can never linger in the form.
      setWf(blank());
    }
  }, [workflowId]);

  const setAgent = (i, agent) =>
    setWf((w) => ({ ...w, agents: w.agents.map((a, j) => (j === i ? agent : a)) }));
  const addAgent = () =>
    setWf((w) => ({ ...w, agents: [...w.agents, { ...newAgent(), id: uid() }] }));
  const removeAgent = (i) =>
    setWf((w) => {
      const gone = w.agents[i]?.id;
      return {
        ...w,
        agents: w.agents.filter((_, j) => j !== i),
        // Drop any wiring that pointed at the deleted agent.
        edges: (w.edges || []).filter((e) => e.source !== gone && e.target !== gone),
      };
    });
  const moveAgent = (i, dir) =>
    setWf((w) => {
      const agents = [...w.agents];
      const j = i + dir;
      if (j < 0 || j >= agents.length) return w;
      [agents[i], agents[j]] = [agents[j], agents[i]];
      return { ...w, agents };
    });

  async function save() {
    setSaving(true);
    const { id, ...rest } = wf; // never send an id on create — the server mints it
    const payload = {
      ...(editing ? wf : rest),
      schedule: wf.trigger_type === "schedule" ? wf.schedule : null,
      // `order` here is just the list position; when edges exist the server
      // recomputes order/parallel_group from the graph (single source of truth).
      agents: wf.agents.map((a, i) => ({ ...a, order: i })),
      edges: wf.edges || [],
    };
    try {
      const saved = editing
        ? await api.updateWorkflow(workflowId, payload)
        : await api.createWorkflow(payload);
      navigate(`/run/${saved.id}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{editing ? "Edit workflow" : "New workflow"}</h1>
        <div className="flex gap-2">
          <button onClick={() => navigate("/")}
            className="rounded-lg border border-edge px-4 py-2 text-sm text-gray-300 hover:bg-panel">
            Cancel
          </button>
          <button onClick={save} disabled={saving}
            className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
            {saving ? "Saving…" : "Save & run →"}
          </button>
        </div>
      </div>

      <div className="grid gap-3 rounded-2xl border border-edge bg-ink/40 p-5 md:grid-cols-2">
        <label className="text-xs text-gray-400">
          Name
          <input value={wf.name} onChange={(e) => setWf({ ...wf, name: e.target.value })}
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm outline-none focus:border-accent" />
        </label>
        <label className="text-xs text-gray-400">
          Trigger
          <select value={wf.trigger_type} onChange={(e) => setWf({ ...wf, trigger_type: e.target.value })}
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm outline-none focus:border-accent">
            <option value="manual">manual</option>
            <option value="schedule">schedule (cron)</option>
            <option value="webhook">webhook</option>
          </select>
        </label>
        <label className="text-xs text-gray-400 md:col-span-2">
          Description
          <input value={wf.description} onChange={(e) => setWf({ ...wf, description: e.target.value })}
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm outline-none focus:border-accent" />
        </label>
        {wf.trigger_type === "schedule" && (
          <label className="text-xs text-gray-400">
            Cron schedule
            <input value={wf.schedule} onChange={(e) => setWf({ ...wf, schedule: e.target.value })}
              placeholder="*/30 * * * *"
              className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm outline-none focus:border-accent" />
          </label>
        )}
        {wf.trigger_type === "webhook" && editing && (
          <div className="text-xs text-gray-400">
            Webhook URL
            <code className="mt-1 block rounded-lg border border-edge bg-ink px-3 py-2 text-[11px] text-accent">
              POST /api/webhooks/{workflowId}
            </code>
          </div>
        )}
        <label className="text-xs text-gray-400">
          Cost cap (USD, optional)
          <input type="number" step="0.01" value={wf.cost_cap ?? ""}
            onChange={(e) => setWf({ ...wf, cost_cap: e.target.value === "" ? null : Number(e.target.value) })}
            placeholder="none"
            className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm outline-none focus:border-accent" />
        </label>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
            Agents ({wf.agents.length})
          </h2>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-edge p-0.5 text-xs">
              {["canvas", "list"].map((v) => (
                <button key={v} onClick={() => setView(v)}
                  className={`rounded px-3 py-1 ${
                    view === v ? "bg-accent text-white" : "text-gray-400 hover:text-gray-200"
                  }`}>
                  {v === "canvas" ? "⬡ Canvas" : "☰ List"}
                </button>
              ))}
            </div>
            <button onClick={addAgent}
              className="rounded-lg border border-edge px-3 py-1.5 text-sm text-accent hover:bg-panel">
              + Add agent
            </button>
          </div>
        </div>

        {view === "canvas" && (
          <div className="mb-3 space-y-2">
            <GraphEditor
              agents={wf.agents}
              edges={wf.edges || []}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onChange={(agents, edges) => setWf((w) => ({ ...w, agents, edges }))}
            />
            <p className="text-[11px] text-gray-500">
              Drag nodes to arrange · drag from a node’s right dot to another’s left dot to
              connect · agents with no path between them run in parallel · click a node to edit it
              below.
            </p>
          </div>
        )}

        <div className="space-y-3">
          {wf.agents
            // On the canvas, show only the agent whose node is selected —
            // otherwise the full stack of editors buries it.
            .map((agent, i) => ({ agent, i }))
            .filter(({ agent }) =>
              view === "list" || !selectedId || agent.id === selectedId)
            .map(({ agent, i }) => (
              <AgentEditor
                key={agent.id || i}
                agent={agent}
                index={i}
                count={wf.agents.length}
                onChange={setAgent}
                onMove={moveAgent}
                onRemove={removeAgent}
              />
            ))}
        </div>
      </div>
    </div>
  );
}
