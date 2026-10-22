import React, { useEffect, useRef, useState } from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { useAuth } from "./auth/AuthContext.jsx";
import { ErrorNotice } from "./components/forms.jsx";
import Home from "./pages/Home.jsx";
import Login from "./pages/Login.jsx";
import CreateRecord from "./pages/CreateRecord.jsx";
import UpdateRecord from "./pages/UpdateRecord.jsx";
import DeleteRecord from "./pages/DeleteRecord.jsx";
import BikeShare from "./pages/BikeShare.jsx";
import { BikeRunSession } from "./BikeRunContext.jsx";

function RequireAuth({ children, roles }) {
  const { user } = useAuth();
  if (user && roles && !roles.includes(user.role)) return (
    <section className="panel form-panel">
      <h1>Permission required</h1>
      <p role="alert">Your {user.role} role cannot perform this action.</p>
      <Link to="/">Back to listings</Link>
    </section>
  );
  return user ? (
    children
  ) : (
    <section className="panel form-panel">
      <h1>Login required</h1>
      <p>Log in to view and manage rental listings.</p>
      <Link className="button" to="/login">
        Log in
      </Link>
    </section>
  );
}

function SelectedRecord({ kind }) {
  const [params] = useSearchParams();
  const raw = params.get("id");
  const id = Number(raw);
  if (!raw || !/^[1-9]\d*$/.test(raw) || !Number.isSafeInteger(id))
    return (
      <section className="panel">
        <h1>Select a listing</h1>
        <p role="alert">
          Choose a listing from the home page to {kind}. A valid positive
          listing ID is required.
        </p>
        <Link to="/">Back to listings</Link>
      </section>
    );
  return kind === "update" ? (
    <UpdateRecord key={id} id={id} />
  ) : (
    <DeleteRecord key={id} id={id} />
  );
}

export default function App() {
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const main = useRef(null);
  const logoutLock = useRef(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    main.current?.focus();
  }, [location.pathname, location.search]);
  useEffect(() => {
    if (auth.status === "expired") navigate("/login", { replace: true });
  }, [auth.status, navigate]);
  async function logout() {
    if (logoutLock.current) return;
    logoutLock.current = true;
    setLoggingOut(true);
    setError("");
    try {
      const operation = auth.logout();
      navigate("/login");
      await operation;
    } catch (failure) {
      setError(failure.message);
    } finally {
      logoutLock.current = false;
      setLoggingOut(false);
    }
  }
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <div className="header-inner">
          <Link className="brand" to="/">
            Rental Housing <span>Listings</span>
          </Link>
          <nav aria-label="Main navigation">
            <NavLink to="/" end>
              Home
            </NavLink>
            {auth.user ? (
              <>
                {["writer", "moderator"].includes(auth.user.role) && <NavLink to="/create">Add listing</NavLink>}
                <NavLink to="/bikeshare">Bike-share</NavLink>
                <button
                  className="secondary"
                  onClick={logout}
                  disabled={loggingOut}
                >
                  {loggingOut ? "Logging out…" : "Log out"}
                </button>
              </>
            ) : (
              <NavLink to="/login">Log in</NavLink>
            )}
          </nav>
        </div>
      </header>
      <main id="main" ref={main} tabIndex={-1}>
        <div className="session-line">
          {auth.user
            ? `Signed in as ${auth.user.name} · ${auth.user.role}`
            : "A place to find your next home"}
        </div>
        <ErrorNotice error={error} />
          <BikeRunSession key={auth.user?.id ?? "guest"}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <Home />
                </RequireAuth>
              }
            />
            <Route
              path="/bikeshare"
              element={
                <RequireAuth>
                  <BikeShare key={auth.user?.id} />
                </RequireAuth>
              }
            />
            <Route
              path="/create"
              element={
                <RequireAuth roles={["writer", "moderator"]}>
                  <CreateRecord />
                </RequireAuth>
              }
            />
            <Route
              path="/update"
              element={
                <RequireAuth roles={["writer", "moderator"]}>
                  <SelectedRecord kind="update" />
                </RequireAuth>
              }
            />
            <Route
              path="/delete"
              element={
                <RequireAuth roles={["moderator"]}>
                  <SelectedRecord kind="delete" />
                </RequireAuth>
              }
            />
            <Route
              path="*"
              element={
                <section className="panel">
                  <h1>Page not found</h1>
                  <Link to="/">Back to listings</Link>
                </section>
              }
            />
          </Routes>
          </BikeRunSession>
      </main>
      <footer>Rental Housing Listings · DATA 260 · s6102</footer>
    </>
  );
}
