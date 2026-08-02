import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker the backend is reachable as http://backend:8000; locally it's
// http://localhost:8000. Override with the BACKEND_URL env var.
const backend = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      // Proxy API + WebSocket to the FastAPI backend during dev.
      "/api": { target: backend, changeOrigin: true, ws: true },
    },
  },
});
