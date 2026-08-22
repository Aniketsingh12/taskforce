// WebSocket helper for the live-run path.
//
// Opens a socket to the backend's /api/runs/ws endpoint, sends the run request,
// and forwards each parsed event to the caller. In dev the Vite dev-server
// proxies /api (including the WebSocket upgrade) to the FastAPI backend at the
// SAME origin — see vite.config.js. In production the frontend (Vercel) and
// backend (Railway/Render) are on different origins, so when VITE_API_URL is
// set the socket is opened against THAT origin instead of the page's own —
// otherwise it would try to reach a backend that doesn't exist on Vercel.
const API_ORIGIN = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");

function wsUrl() {
  if (API_ORIGIN) {
    const proto = API_ORIGIN.startsWith("https:") ? "wss" : "ws";
    const host = API_ORIGIN.replace(/^https?:\/\//, "");
    return `${proto}://${host}/api/runs/ws`;
  }
  // Same-origin fallback: match the page protocol (http → ws, https → wss).
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/runs/ws`;
}

export function startRunStream({ workflowId, input, onEvent, onClose }) {
  const ws = new WebSocket(wsUrl());

  // As soon as the socket is open, tell the backend which workflow to run.
  // The admin token rides in this first message because a browser can't set
  // custom headers on a WebSocket handshake. Without it the run still works —
  // the server just forces it onto the free demo model.
  ws.onopen = () => {
    let token = "";
    try {
      token = localStorage.getItem("taskforce_admin_token") || "";
    } catch {
      /* storage unavailable → run in demo mode */
    }
    ws.send(JSON.stringify({
      workflow_id: workflowId,
      input,
      ...(token ? { admin_token: token } : {}),
    }));
  };

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
