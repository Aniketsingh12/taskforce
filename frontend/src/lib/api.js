// Thin REST client for the TaskForce backend.
const BASE = "/api";

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
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
