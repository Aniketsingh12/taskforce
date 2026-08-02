import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

// Assign tools (MCP-backed in the full version) to an agent. Value: string[].
export default function ToolPicker({ value = [], onChange }) {
  const [tools, setTools] = useState([]);

  useEffect(() => {
    api.tools().then(setTools).catch(() => setTools([]));
  }, []);

  function toggle(name) {
    onChange(value.includes(name) ? value.filter((t) => t !== name) : [...value, name]);
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {tools.length === 0 && <span className="text-xs text-gray-500">No tools available</span>}
      {tools.map((t) => {
        const on = value.includes(t.name);
        return (
          <button
            type="button"
            key={t.name}
            onClick={() => toggle(t.name)}
            title={t.description}
            className={`rounded-full px-2.5 py-1 text-[11px] transition ${
              on ? "bg-accent/25 text-accent" : "bg-ink text-gray-400 hover:text-gray-200"
            }`}
          >
            🔧 {t.name}
          </button>
        );
      })}
    </div>
  );
}
