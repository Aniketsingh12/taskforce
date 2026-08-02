import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import CostBadge from "../components/CostBadge.jsx";

const STATUS_COLOR = {
  done: "text-emerald-300",
  failed: "text-red-300",
  running: "text-accent",
  queued: "text-gray-400",
  cancelled: "text-gray-400",
  skipped: "text-gray-500",
};

export default function RunHistory() {
  const [runs, setRuns] = useState([]);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.listRuns().then((r) => alive && setRuns(r)).catch(() => {});
    load();
    // Runs started elsewhere (schedule, webhook, another tab) finish in the
    // background, so poll while anything is still in flight.
    const id = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Run History</h1>

      {runs.length === 0 && (
        <p className="text-sm text-gray-400">No runs yet. Trigger one from the Dashboard.</p>
      )}

      {runs.map((run) => (
        <div key={run.id} className="rounded-xl border border-edge bg-panel">
          <button
            onClick={() => setExpanded(expanded === run.id ? null : run.id)}
            className="flex w-full items-center justify-between px-4 py-3 text-left"
          >
            <div>
              <span className="font-medium">{run.workflow_name}</span>
              <span className={`ml-3 text-sm ${STATUS_COLOR[run.status]}`}>{run.status}</span>
              <span className="ml-3 text-xs text-gray-500">
                {new Date(run.started_at).toLocaleString()}
              </span>
            </div>
            <CostBadge cost={run.total_cost} tokens={run.total_tokens} />
          </button>

          {expanded === run.id && (
            <div className="space-y-3 border-t border-edge px-4 py-3">
              {run.error && <p className="text-sm text-red-300">Error: {run.error}</p>}
              {run.traces.map((t) => (
                <div key={t.id} className="rounded-lg bg-ink/60 p-3">
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-semibold">
                      {t.agent_role}
                      {t.status === "skipped" && (
                        <span className="ml-2 rounded-full bg-panel px-2 py-0.5 text-[11px] font-normal text-gray-400">
                          skipped — condition not met
                        </span>
                      )}
                    </span>
                    {t.status !== "skipped" && (
                      <span className="flex items-center gap-2 text-xs text-gray-400">
                        <span>{t.model_used}</span>
                        <span>{t.latency_ms}ms</span>
                        <CostBadge cost={t.cost_usd} tokens={t.prompt_tokens + t.completion_tokens} />
                      </span>
                    )}
                  </div>
                  {/* A skipped agent has no output — say so instead of showing
                      an empty box that reads like a failure. */}
                  {t.status !== "skipped" && (
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-gray-300">
                      {t.output}
                    </pre>
                  )}
                </div>
              ))}
              {run.final_output && (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
                  <div className="mb-1 text-xs font-semibold text-emerald-200">Final deliverable</div>
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-xs text-gray-100">
                    {run.final_output}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
