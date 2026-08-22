import { useState } from "react";
import { useAuth } from "../lib/auth.jsx";

// Header control showing which mode you're in, with a way to unlock admin.
//
// Renders nothing when the deployment has no ADMIN_TOKEN configured (local dev)
// — there's no mode to be in, so a badge would just be noise.
export default function AccessBadge() {
  const { status, admin, demoMode, signIn, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!status?.gating_enabled) return null;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      // The server decides — signIn discards the token if it's rejected.
      if (await signIn(value)) {
        setOpen(false);
        setValue("");
      } else {
        setError("That token wasn't accepted.");
      }
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  if (admin) {
    const spent = status?.spent_today;
    const limit = status?.daily_limit;
    return (
      <div className="flex items-center gap-2">
        <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300">
          🔓 admin
        </span>
        {typeof spent === "number" && (
          <span className="text-[11px] text-gray-500" title="Spend today across all runs">
            ${spent.toFixed(4)}
            {limit ? ` / $${limit}` : ""}
          </span>
        )}
        <button
          onClick={signOut}
          className="rounded px-2 py-0.5 text-[11px] text-gray-400 hover:text-gray-200"
        >
          lock
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title={demoMode ? `Runs use ${status?.demo_model} (free)` : ""}
        className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] text-amber-300 hover:bg-amber-500/25"
      >
        🔒 demo mode
      </button>
      {open && (
        <form
          onSubmit={submit}
          className="absolute right-0 z-50 mt-2 w-72 rounded-xl border border-edge bg-panel p-3 shadow-xl"
        >
          <p className="mb-2 text-[11px] text-gray-400">
            Demo runs use the free <code className="text-gray-300">{status?.demo_model}</code>{" "}
            model. Enter the admin token to enable real models and editing.
          </p>
          <input
            type="password"
            value={value}
            autoFocus
            onChange={(e) => setValue(e.target.value)}
            placeholder="admin token"
            className="w-full rounded border border-edge bg-ink px-2 py-1.5 text-xs outline-none focus:border-accent"
          />
          {error && <p className="mt-1 text-[11px] text-red-300">{error}</p>}
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded px-2 py-1 text-[11px] text-gray-400 hover:text-gray-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || !value.trim()}
              className="rounded bg-accent px-3 py-1 text-[11px] text-white disabled:opacity-50"
            >
              {busy ? "Checking…" : "Unlock"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
