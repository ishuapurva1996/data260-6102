import React, { createContext, useContext, useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import { advanceAuthEpoch, getAuthEpoch, request } from "../api/client.js";
import { clearRentals } from "../features/rentals/rentalsSlice.js";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const dispatch = useDispatch();
  const [auth, setAuth] = useState({ status: "checking", user: null });
  const [attempt, setAttempt] = useState(0);
  function resetSession() {
    const epoch = advanceAuthEpoch();
    dispatch(clearRentals());
    return epoch;
  }
  useEffect(() => {
    const controller = new AbortController();
    const epoch = getAuthEpoch();
    const expired = () => {
      advanceAuthEpoch();
      dispatch(clearRentals());
      setAuth({ status: "expired", user: null });
    };
    window.addEventListener("session-expired", expired);
    request("/auth/me", { signal: controller.signal, notifyUnauthorized: false })
      .then(({ user }) => {
        if (!controller.signal.aborted && epoch === getAuthEpoch())
          setAuth({ status: "authenticated", user });
      })
      .catch((error) => {
        if (controller.signal.aborted || epoch !== getAuthEpoch()) return;
        dispatch(clearRentals());
        setAuth({ status: error.status === 401 ? "anonymous" : "error", user: null, error: error.message });
      });
    return () => {
      controller.abort();
      window.removeEventListener("session-expired", expired);
    };
  }, [attempt, dispatch]);
  async function login(email, password) {
    const epoch = resetSession();
    const { user } = await request("/auth/login", {
      method: "POST", body: { email, password }, notifyUnauthorized: false,
    });
    if (epoch !== getAuthEpoch()) throw new Error("This login was superseded. Please try again.");
    setAuth({ status: "authenticated", user });
  }
  async function logout() {
    const epoch = resetSession();
    setAuth({ status: "anonymous", user: null });
    try { await request("/auth/logout", { method: "POST", notifyUnauthorized: false }); }
    catch (error) {
      if (epoch === getAuthEpoch()) throw new Error(`Local data cleared, but logout could not be confirmed. ${error.message}`);
    }
  }
  function retry() {
    resetSession();
    setAuth({ status: "checking", user: null });
    setAttempt((value) => value + 1);
  }
  return <AuthContext.Provider value={{ ...auth, login, logout, retry }}>{children}</AuthContext.Provider>;
}
