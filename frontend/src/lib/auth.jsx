import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api.js";

// Admin access for a publicly-shared deployment.
//
// The app is meant to be shareable: a visitor can browse and run workflows, but
// their runs are forced onto the free demo model and they can't change data.
// Holding the admin token unlocks real models and editing.
//
// The token lives in localStorage (not a cookie) because it's only ever sent
// as an explicit X-Admin-Token header — nothing is attached automatically to
// cross-site requests, so there's no CSRF surface to worry about.

const STORAGE_KEY = "taskforce_admin_token";

export function getToken() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return ""; // private browsing / storage disabled
  }
}

function storeToken(token) {
  try {
    if (token) localStorage.setItem(STORAGE_KEY, token);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* non-fatal: the token just won't persist across reloads */
  }
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // `null` until the first status call resolves, so the UI can avoid flashing
  // "demo mode" at an admin during page load.
  const [status, setStatus] = useState(null);

  const refresh = useCallback(async () => {
    let next;
    try {
      next = await api.authStatus();
    } catch {
      // Backend unreachable — assume the most restrictive posture rather than
      // showing admin controls that would fail on click.
      next = { gating_enabled: true, admin: false, demo_mode: true };
    }
    setStatus(next);
    return next;
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signIn = useCallback(
    async (token) => {
      // Store first so the refresh call carries the token, then let the SERVER
      // decide whether it's valid — the client never validates it locally.
      storeToken(token.trim());
      const next = await refresh();
      if (!next.admin) storeToken("");  // reject a bad token instead of keeping it
      return next.admin;
    },
    [refresh]
  );

  const signOut = useCallback(async () => {
    storeToken("");
    await refresh();
  }, [refresh]);

  // Until status loads, treat the user as an admin for RENDERING purposes only
  // (so controls don't visibly pop in). The server is the real gate — a
  // non-admin clicking through just gets a 401.
  const admin = status ? status.admin : true;
  const demoMode = status ? status.demo_mode : false;

  return (
    <AuthContext.Provider
      value={{ status, admin, demoMode, loading: status === null, signIn, signOut, refresh }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
