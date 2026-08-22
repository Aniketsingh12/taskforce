import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider } from "./lib/auth.jsx";
import AccessBadge from "./components/AccessBadge.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import RunView from "./pages/RunView.jsx";
import RunHistory from "./pages/RunHistory.jsx";
import WorkflowBuilder from "./pages/WorkflowBuilder.jsx";
import Models from "./pages/Models.jsx";

function NavLink({ to, children }) {
  const { pathname } = useLocation();
  const active = pathname === to || (to !== "/" && pathname.startsWith(to));
  return (
    <Link
      to={to}
      className={`rounded-lg px-3 py-1.5 text-sm transition ${
        active ? "bg-accent/20 text-accent" : "text-gray-300 hover:bg-panel"
      }`}
    >
      {children}
    </Link>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

function AppShell() {
  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col px-5">
      <header className="flex items-center justify-between border-b border-edge py-4">
        <Link to="/" className="flex items-center gap-2">
          <span className="text-xl">⚡</span>
          <span className="text-lg font-bold tracking-tight">TaskForce</span>
          <span className="rounded bg-panel px-2 py-0.5 text-[11px] text-gray-400">MVP</span>
        </Link>
        <nav className="flex items-center gap-1">
          <NavLink to="/">Dashboard</NavLink>
          <NavLink to="/builder">Builder</NavLink>
          <NavLink to="/models">Models</NavLink>
          <NavLink to="/history">Run History</NavLink>
          <div className="ml-2 border-l border-edge pl-2">
            <AccessBadge />
          </div>
        </nav>
      </header>

      <main className="flex-1 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          {/* Distinct keys force a remount when switching between "new" and
              "edit", so the builder can't carry one workflow's data into the
              other (which previously let a "new" save overwrite the original). */}
          <Route path="/builder" element={<WorkflowBuilder key="new" />} />
          <Route path="/builder/:workflowId" element={<WorkflowBuilder key="edit" />} />
          <Route path="/models" element={<Models />} />
          <Route path="/run/:workflowId" element={<RunView />} />
          <Route path="/history" element={<RunHistory />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="border-t border-edge py-3 text-center text-xs text-gray-500">
        Agents run on local (Ollama) · hosted (OpenRouter) · or the built-in demo model
      </footer>
    </div>
  );
}
