import CostBadge from "./CostBadge.jsx";

// Read-only summary of an agent's configuration (used on the Dashboard).
export default function AgentCard({ agent, index }) {
  return (
    <div className="rounded-xl border border-edge bg-panel p-4">
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent/20 text-xs text-accent">
            {index + 1}
          </span>
          <span className="font-semibold">{agent.role}</span>
        </div>
        <span className="rounded bg-ink px-2 py-0.5 text-[11px] text-gray-300">
          {agent.model_provider}:{agent.model_name}
        </span>
      </div>
      <p className="line-clamp-2 text-xs text-gray-400">{agent.instructions}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {agent.tools.map((t) => (
          <span key={t} className="rounded bg-ink px-2 py-0.5 text-[11px] text-gray-300">
            🔧 {t}
          </span>
        ))}
        {/* Execution mode — without these a parallel or conditional workflow
            looks identical to a plain sequential one. */}
        {agent.parallel_group != null && (
          <span className="rounded bg-sky-500/15 px-2 py-0.5 text-[11px] text-sky-300">
            ⇉ parallel {agent.parallel_group}
          </span>
        )}
        {agent.condition && (
          <span className="rounded bg-amber-500/15 px-2 py-0.5 text-[11px] text-amber-300">
            ? if “{agent.condition}”
          </span>
        )}
        <span className="text-[11px] text-gray-500">out: {agent.output_format}</span>
        {agent.model_provider === "mock" || agent.model_provider === "ollama" ? (
          <CostBadge cost={0} tokens={0} />
        ) : null}
      </div>
    </div>
  );
}
