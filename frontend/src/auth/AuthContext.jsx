import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { useDispatch } from "react-redux";
import { advanceAuthEpoch, getAuthEpoch, request, setAccessToken } from "../api/client.js";
import { clearRentals } from "../features/rentals/rentalsSlice.js";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const dispatch = useDispatch();
  const [auth, setAuth] = useState({ status: "anonymous", user: null });
  const expiry = useRef(null);
  function resetSession() {
    clearTimeout(expiry.current);
    setAccessToken(null);
    dispatch(clearRentals());
    return advanceAuthEpoch();
  }
  useEffect(() => {
    const expired = () => {
      resetSession();
      setAuth({ status: "expired", user: null });
    };
    window.addEventListener("token-expired", expired);
    return () => {
      clearTimeout(expiry.current);
      window.removeEventListener("token-expired", expired);
    };
  }, [dispatch]);
  async function login(username, password) {
    const epoch = resetSession();
    setAuth({ status: "anonymous", user: null });
    try {
      const { access_token, expires_in } = await request("/auth/login", {
        method: "POST", body: { username, password }, authenticate: false, notifyUnauthorized: false,
      });
      if (epoch !== getAuthEpoch()) throw new Error("This login was superseded. Please try again.");
      setAccessToken(access_token);
      const { user } = await request("/auth/me", { notifyUnauthorized: false });
      if (epoch !== getAuthEpoch()) throw new Error("This login was superseded. Please try again.");
      setAuth({ status: "authenticated", user });
      expiry.current = setTimeout(() => window.dispatchEvent(new Event("token-expired")),
        expires_in * 1000);
    } catch (error) {
      if (epoch === getAuthEpoch()) resetSession();
      throw error;
    }
  }
  async function logout() {
    resetSession();
    setAuth({ status: "anonymous", user: null });
  }
  return <AuthContext.Provider value={{ ...auth, login, logout }}>{children}</AuthContext.Provider>;
}
