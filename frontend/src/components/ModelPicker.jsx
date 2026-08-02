import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

// Per-agent model selection. Value: { provider, model }. Groups local (free)
// vs hosted (billed) vs demo so the cost trade-off is visible while building.
export default function ModelPicker({ value, onChange }) {
  const [models, setModels] = useState(null);

  useEffect(() => {
    api.models().then(setModels).catch(() => setModels({ local: [], hosted: [], demo: [] }));
  }, []);

  const current = `${value.provider}:${value.model}`;

  function pick(e) {
    const [provider, ...rest] = e.target.value.split(":");
    onChange({ provider, model: rest.join(":") });
  }

  const group = (label, list, free) =>
    list?.length ? (
      <optgroup key={label} label={`${label}${free ? " — free" : ""}`}>
        {list.map((m) => (
          <option key={`${m.provider}:${m.model}`} value={`${m.provider}:${m.model}`}>
            {m.model}
            {!free && m.cost_out ? `  ($${m.cost_out}/1M out)` : ""}
          </option>
        ))}
      </optgroup>
    ) : null;

  return (
    <select
      value={current}
      onChange={pick}
      className="w-full rounded-lg border border-edge bg-ink px-2 py-1.5 text-xs outline-none focus:border-accent"
    >
      {!models && <option>Loading…</option>}
      {models && (
        <>
          {group("Demo", models.demo, true)}
          {group("Local (Ollama)", models.local, true)}
          {group("Hosted (OpenRouter)", models.hosted, false)}
        </>
      )}
    </select>
  );
}
