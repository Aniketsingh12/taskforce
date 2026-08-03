import CostBadge from "./CostBadge.jsx";

// One expandable panel per agent showing its streaming/finished output.
export default function LiveTrace({
  agents = [], outputs = {}, traces = {}, toolCalls = {}, activeId,
}) {
  return (
    <div className="space-y-3">
      {agents.map((a) => {
        const trace = traces[a.id];
        const text = trace?.output ?? outputs[a.id] ?? "";
        const calls = toolCalls[a.id] || [];
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
            {/* What the model decided to call, and with what — the reasoning
                chain, not just the final answer. */}
            {calls.length > 0 && (
              <div className="flex flex-wrap gap-1.5 border-b border-edge px-4 py-2">
                {calls.map((c, i) => (
                  <span key={i}
                    className="rounded-full bg-sky-500/15 px-2 py-0.5 font-mono text-[11px] text-sky-300"
                    title={JSON.stringify(c.arguments)}>
                    🔧 {c.tool}({Object.values(c.arguments || {})[0] ?? ""})
                  </span>
                ))}
              </div>
            )}
            {/* For JSON agents show the PARSED value — that's what the next
                agent actually receives — and flag it when parsing failed. */}
            {trace?.output_json != null ? (
              <div className="px-4 py-3">
                <div className="mb-1 text-[10px] uppercase tracking-wide text-emerald-300">
                  parsed json
                </div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap font-mono text-xs text-emerald-100">
                  {JSON.stringify(trace.output_json, null, 2)}
                </pre>
              </div>
            ) : (
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap px-4 py-3 text-sm text-gray-200">
                {text || (isActive ? "…" : "Waiting")}
                {isActive && <span className="animate-pulse">▍</span>}
              </pre>
            )}
            {trace?.parse_error && (
              <div className="border-t border-amber-500/30 px-4 py-2 text-[11px] text-amber-300">
                ⚠ expected JSON but couldn’t parse it: {trace.parse_error}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
