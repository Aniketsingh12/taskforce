import CostBadge from "./CostBadge.jsx";

// One expandable panel per agent showing its streaming/finished output.
export default function LiveTrace({ agents = [], outputs = {}, traces = {}, activeId }) {
  return (
    <div className="space-y-3">
      {agents.map((a) => {
        const trace = traces[a.id];
        const text = trace?.output ?? outputs[a.id] ?? "";
        const isActive = activeId === a.id;
        return (
          <div key={a.id} className="rounded-xl border border-edge bg-panel">
            <div className="flex items-center justify-between border-b border-edge px-4 py-2">
              <div className="flex items-center gap-2">
                <span
                  className={`h-2 w-2 rounded-full ${
                    isActive ? "bg-accent" : trace ? "bg-emerald-400" : "bg-gray-600"
                  }`}
                />
                <span className="font-semibold">{a.role}</span>
                {trace?.tools_called?.length > 0 && (
                  <span className="text-[11px] text-gray-400">
                    tools: {trace.tools_called.join(", ")}
                  </span>
                )}
              </div>
              {trace && (
                <div className="flex items-center gap-2 text-[11px] text-gray-400">
                  <span>{trace.latency_ms}ms</span>
                  <CostBadge cost={trace.cost_usd} tokens={trace.prompt_tokens + trace.completion_tokens} />
                </div>
              )}
            </div>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap px-4 py-3 text-sm text-gray-200">
              {text || (isActive ? "…" : "Waiting")}
              {isActive && <span className="animate-pulse">▍</span>}
            </pre>
          </div>
        );
      })}
    </div>
  );
}
