// WebSocket helper for the live-run path.
//
// Opens a socket to the backend's /api/runs/ws endpoint, sends the run request,
// and forwards each parsed event to the caller. The dev server proxies /api
// (including WebSocket upgrades) to the FastAPI backend — see vite.config.js.
export function startRunStream({ workflowId, input, onEvent, onClose }) {
  // Match the page protocol so it works under both http (ws) and https (wss).
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/api/runs/ws`);

  // As soon as the socket is open, tell the backend which workflow to run.
  ws.onopen = () => ws.send(JSON.stringify({ workflow_id: workflowId, input }));

  // Each message is one JSON event (run_started, token, agent_completed, …).
  ws.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data));
    } catch {
      /* ignore malformed frames */
    }
  };

  ws.onclose = () => onClose && onClose();
  return ws; // caller keeps a ref so it can close the socket on unmount
}
