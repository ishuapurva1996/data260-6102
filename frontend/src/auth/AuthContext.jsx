import React, { createContext, useContext, useEffect, useState } from "react";
import { advanceAuthEpoch, request } from "../api/client.js";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState({ status: "checking", user: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const expired = () => {
      advanceAuthEpoch();
      setAuth({ status: "expired", user: null });
    };
    window.addEventListener("session-expired", expired);
    request("/auth/me", {
      signal: controller.signal,
      notifyUnauthorized: false,
    })
      .then(({ user }) => {
        if (!controller.signal.aborted)
          setAuth({ status: "authenticated", user });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setAuth({
          status: error.status === 401 ? "anonymous" : "error",
          user: null,
          error: error.message,
        });
      });
    return () => {
      controller.abort();
      window.removeEventListener("session-expired", expired);
    };
  }, [attempt]);
  async function login(email, password) {
    advanceAuthEpoch();
    const { user } = await request("/auth/login", {
      method: "POST",
      body: { email, password },
      notifyUnauthorized: false,
    });
    setAuth({ status: "authenticated", user });
  }
  async function logout() {
    advanceAuthEpoch();
    await request("/auth/logout", { method: "POST" });
    setAuth({ status: "anonymous", user: null });
  }
  function retry() {
    setAuth({ status: "checking", user: null });
    setAttempt((value) => value + 1);
  }
  return (
    <AuthContext.Provider value={{ ...auth, login, logout, retry }}>
      {children}
    </AuthContext.Provider>
  );
}
