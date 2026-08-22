// Thin REST client for the TaskForce backend.
//
// In dev (and Docker Compose) requests go through the Vite dev-server proxy at
// the relative path "/api" — see vite.config.js. In production the frontend
// and backend are on different domains (e.g. Vercel + Railway), so set
// VITE_API_URL to the backend's origin at build time; unset, BASE stays
// relative and same-origin behaviour is unchanged.
const API_ORIGIN = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");
const BASE = `${API_ORIGIN}/api`;

// Read lazily from localStorage rather than importing auth.jsx, which would
// create a circular import (auth.jsx already imports this module).
function adminToken() {
  try {
    return localStorage.getItem("taskforce_admin_token") || "";
  } catch {
    return "";
  }
}

async function req(path, opts = {}) {
  const token = adminToken();
  const res = await fetch(BASE + path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      // Unlocks real models and mutations. Absent = demo mode, which is a
      // valid state, not an error.
      ...(token ? { "X-Admin-Token": token } : {}),
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    // Surface the server's explanation (rate limit hit, budget exhausted, bad
    // token) instead of a bare status code the user can't act on.
    let detail = "";
    try {
      detail = (await res.json())?.detail || "";
    } catch {
      /* non-JSON error body */
    }
    const err = new Error(detail || `${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  authStatus: () => req("/auth/status"),
  listWorkflows: () => req("/workflows"),
  getWorkflow: (id) => req(`/workflows/${id}`),
  workflowGraph: (id) => req(`/workflows/${id}/graph`),
  createWorkflow: (wf) => req("/workflows", { method: "POST", body: JSON.stringify(wf) }),
  updateWorkflow: (id, wf) => req(`/workflows/${id}`, { method: "PUT", body: JSON.stringify(wf) }),
  deleteWorkflow: (id) => req(`/workflows/${id}`, { method: "DELETE" }),
  cloneWorkflow: (id) => req(`/workflows/${id}/clone`, { method: "POST" }),
  triggerRun: (workflow_id, input) =>
    req("/runs/trigger", { method: "POST", body: JSON.stringify({ workflow_id, input }) }),
  listRuns: (workflowId) =>
    req(`/runs${workflowId ? `?workflow_id=${workflowId}` : ""}`),
  getRun: (id) => req(`/runs/${id}`),
  models: () => req("/models"),
  tools: () => req("/tools"),
  stats: () => req("/stats"),
};
