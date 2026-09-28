import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { rentals } from "../api/client.js";

export function ErrorNotice({ error }) {
  return error ? (
    <div className="notice error" role="alert">
      {error}
    </div>
  ) : null;
}

export function TitleFields({ values, onChange }) {
  return (
    <>
      <label>
        Listing title
        <input
          name="listingTitle"
          required
          maxLength={255}
          value={values.listingTitle}
          onChange={onChange}
        />
      </label>
      <label>
        Property address
        <input
          name="propertyAddress"
          required
          maxLength={255}
          value={values.propertyAddress}
          onChange={onChange}
        />
      </label>
    </>
  );
}

// A synchronous lock also blocks a second submit before React renders disabled.
export function useSubmission(action, successMessage) {
  const lock = useRef(false);
  const mounted = useRef(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function submit(event) {
    event.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setPending(true);
    setError("");
    try {
      await action();
      // Home fetches fresh server data. A failed list refresh cannot repeat a write.
      if (mounted.current) navigate("/", { state: { notice: successMessage } });
    } catch (failure) {
      if (mounted.current) setError(failure.message);
    } finally {
      lock.current = false;
      if (mounted.current) setPending(false);
    }
  }
  return { pending, error, submit };
}

export function useSelectedRental(id) {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    rentals
      .get(id, controller.signal)
      .then((record) => {
        if (!controller.signal.aborted) setState({ record, loading: false });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ error: error.message, loading: false });
      });
    return () => controller.abort();
  }, [id]);
  return state;
}

export function RecordState({ loading, error }) {
  return (
    <section className="panel">
      <h1>{loading ? "Loading listing…" : "Listing unavailable"}</h1>
      <ErrorNotice error={error} />
      <Link to="/">Back to listings</Link>
    </section>
  );
}

export function FormActions({ pending, label, danger = false }) {
  return (
    <div className="actions">
      <button
        type="submit"
        className={danger ? "danger" : ""}
        disabled={pending}
      >
        {pending ? "Saving…" : label}
      </button>
      <span>
        {pending ? (
          <span aria-disabled="true">Cancel unavailable while saving</span>
        ) : (
          <Link to="/">Cancel</Link>
        )}
      </span>
    </div>
  );
}
