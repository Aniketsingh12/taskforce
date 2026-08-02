import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

function Stat({ label, value, sub }) {
  return (
    <div className="rounded-xl border border-edge bg-panel px-4 py-3">
      <div className="text-xl font-bold">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-gray-500">{label}</div>
      {sub && <div className="text-[11px] text-gray-400">{sub}</div>}
    </div>
  );
}

export default function StatsBar() {
  const [s, setS] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => api.stats().then((d) => alive && setS(d)).catch(() => {});
    load();
    // Stats change when RUNS happen, which this component can't observe from
    // props — so refresh on a timer rather than on a meaningless prop key.
    const id = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  if (!s) return null;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <Stat label="Total runs" value={s.total_runs} />
      <Stat label="Success rate" value={`${Math.round(s.success_rate * 100)}%`}
        sub={`${s.completed} done · ${s.failed} failed`} />
      <Stat label="Total cost" value={`$${s.total_cost.toFixed(4)}`}
        sub={`${s.total_tokens.toLocaleString()} tokens`} />
      <Stat label="Local vs API" value={`${s.cost_breakdown.local_agents}/${s.cost_breakdown.api_agents}`}
        sub={`agents · $${s.cost_breakdown.api.toFixed(4)} API`} />
      <Stat label="Avg latency" value={`${s.avg_latency_ms}ms`} />
    </div>
  );
}
