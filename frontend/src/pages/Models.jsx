import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

// Free tiers show "—" (no cost). Billed models with no reported price show
// "n/a" rather than "$0", which would read as free.
function price(free, value) {
  if (free) return "—";
  return value ? `$${value}` : "n/a";
}

function ModelTable({ title, rows, free, note }) {
  if (!rows?.length) return null;
  return (
    <section className="rounded-2xl border border-edge bg-ink/40 p-5">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        <span className={`rounded-full px-2 py-0.5 text-[11px] ${free ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"}`}>
          {free ? "FREE" : "billed"}
        </span>
      </div>
      {note && <p className="mb-3 text-xs text-gray-400">{note}</p>}
      <table className="w-full text-sm">
        <thead className="text-left text-[11px] uppercase text-gray-500">
          <tr>
            <th className="pb-2">Provider</th>
            <th className="pb-2">Model</th>
            <th className="pb-2 text-right">In / 1M</th>
            <th className="pb-2 text-right">Out / 1M</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={`${m.provider}:${m.model}`} className="border-t border-edge">
              <td className="py-2 text-gray-400">{m.provider}</td>
              <td className="py-2 font-mono text-xs">{m.model}</td>
              {/* "—" means free for a local row, but "price not reported" for
                  a billed one — rendering a bare $0 there would wrongly read
                  as free. */}
              <td className="py-2 text-right text-gray-300">{price(free, m.cost_in)}</td>
              <td className="py-2 text-right text-gray-300">{price(free, m.cost_out)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function Models() {
  const [models, setModels] = useState(null);

  useEffect(() => {
    api.models().then(setModels).catch(() => setModels({ local: [], hosted: [], demo: [] }));
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Models</h1>
        <p className="text-sm text-gray-400">
          Route each agent to the cheapest model that does its job. Local models are
          free; hosted models are billed per token through the OpenRouter gateway.
        </p>
      </div>
      {!models && <p className="text-sm text-gray-400">Loading…</p>}
      {models && (
        <>
          <ModelTable title="Demo (built-in)" rows={models.demo} free
            note="Offline mock model — powers the zero-setup demo and tests." />
          <ModelTable title="Local — Ollama" rows={models.local} free
            note={
              models.ollama_live
                ? "Live from your Ollama server — these models are pulled and ready. $0 inference."
                : "Ollama isn’t reachable, so these are suggestions, not installed models. Start Ollama and pull one, e.g. `ollama pull llama3.1:8b`."
            } />
          <ModelTable title="Together AI" rows={models.together}
            note={
              models.together_live
                ? "Live from Together's API — this is their current catalog. Open-source models (Llama, DeepSeek, Qwen, Kimi…) at per-token pricing. Cost shows as — because Together doesn't return per-model pricing here; real token counts are still recorded per run."
                : "Set TOGETHER_API_KEY to load Together's live model catalog. Until then this is a suggested default, not a confirmed list."
            } />

          <ModelTable title="Hosted — OpenRouter" rows={models.hosted}
            note="One API key unlocks Claude, GPT, Gemini, Groq-served Llama, and more." />
        </>
      )}
    </div>
  );
}
