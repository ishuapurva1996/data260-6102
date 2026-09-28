import React, { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { ErrorNotice, useSubmission } from "../components/forms.jsx";

export default function Login() {
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { pending, error, submit } = useSubmission(
    () => auth.login(email.trim(), password),
    "You are logged in.",
  );
  if (auth.user) return <Navigate to="/" replace />;
  return (
    <section className="panel form-panel">
      <p className="eyebrow">RENTAL HOUSING LISTINGS</p>
      <h1>Log in</h1>
      <p>Login required to view and manage rental listings.</p>
      {auth.status === "expired" && (
        <p className="notice" role="status">
          Your session expired or is no longer valid. Please log in again.
        </p>
      )}
      <form onSubmit={submit}>
        <fieldset disabled={pending}>
          <label>
            Email
            <input
              name="email"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
        </fieldset>
        <ErrorNotice error={error} />
        <button disabled={pending}>{pending ? "Logging in…" : "Log in"}</button>
      </form>
    </section>
  );
}
