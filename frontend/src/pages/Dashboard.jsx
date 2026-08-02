import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import AgentCard from "../components/AgentCard.jsx";
import StatsBar from "../components/StatsBar.jsx";

const TRIGGER_BADGE = {
  manual: "manual",
  schedule: "⏰ scheduled",
  webhook: "🔗 webhook",
};

export default function Dashboard() {
  const [workflows, setWorkflows] = useState([]);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const load = () => api.listWorkflows().then(setWorkflows).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function clone(id) {
    const wf = await api.cloneWorkflow(id);
    navigate(`/builder/${wf.id}`);
  }

  async function remove(id) {
    if (!confirm("Delete this workflow?")) return;
    await api.deleteWorkflow(id);
    load();
  }

  if (error)
    return (
      <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200">
        Could not reach the API ({error}). Is the backend running on :8000?
      </div>
    );

  const templates = workflows.filter((w) => w.is_template);
  const custom = workflows.filter((w) => !w.is_template);

  const card = (wf) => (
    <section key={wf.id} className="rounded-2xl border border-edge bg-ink/40 p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">{wf.name}</h2>
            <span className="rounded-full bg-panel px-2 py-0.5 text-[11px] text-gray-400">
              {TRIGGER_BADGE[wf.trigger_type] || wf.trigger_type}
            </span>
            {wf.is_template && (
              <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] text-accent">template</span>
            )}
          </div>
          <p className="text-sm text-gray-400">{wf.description}</p>
        </div>
        <div className="flex flex-shrink-0 gap-2">
          <button onClick={() => navigate(`/run/${wf.id}`)}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">
            Run →
          </button>
          {wf.is_template ? (
            <button onClick={() => clone(wf.id)}
              className="rounded-lg border border-edge px-3 py-2 text-sm text-gray-300 hover:bg-panel">
              Clone
            </button>
          ) : (
            <>
              <button onClick={() => navigate(`/builder/${wf.id}`)}
                className="rounded-lg border border-edge px-3 py-2 text-sm text-gray-300 hover:bg-panel">
                Edit
              </button>
              <button onClick={() => remove(wf.id)}
                className="rounded-lg border border-edge px-3 py-2 text-sm text-red-300 hover:bg-panel">
                Delete
              </button>
            </>
          )}
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {wf.agents
          .slice()
          .sort((a, b) => a.order - b.order)
          .map((agent, i) => (
            <AgentCard key={agent.id} agent={agent} index={i} />
          ))}
      </div>
    </section>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-gray-400">
            Teams of AI agents that complete a workflow end to end.
          </p>
        </div>
        <button onClick={() => navigate("/builder")}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">
          + New workflow
        </button>
      </div>

      <StatsBar />

      {custom.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">Your workflows</h2>
          {custom.map(card)}
        </div>
      )}

      <div className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">Templates</h2>
        {templates.map(card)}
      </div>

      {workflows.length === 0 && !error && (
        <div className="text-sm text-gray-400">Loading workflows…</div>
      )}
    </div>
  );
}
