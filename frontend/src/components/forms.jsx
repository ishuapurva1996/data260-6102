import React, { useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { listManagers } from "../api/client.js";
import { fetchRental } from "../features/rentals/rentalsSlice.js";

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
      if (mounted.current) setError(typeof failure === "string" ? failure : failure.message);
    } finally {
      lock.current = false;
      if (mounted.current) setPending(false);
    }
  }
  return { pending, error, submit };
}

export function useSelectedRental(id) {
  const dispatch = useDispatch();
  const visitId = useId();
  const state = useSelector((store) => store.rentals);
  const isCurrentVisit = state.detailId === id && state.detailVisitId === visitId;
  // A reopened editor must read after a write from the previous visit settles.
  // The already initialized editor stays mounted while its own write completes.
  const waitingForPriorMutation = !isCurrentVisit &&
    state.mutations[`record:${id}`]?.status === "pending";
  useEffect(() => {
    if (waitingForPriorMutation) return;
    const operation = dispatch(fetchRental({ id, visitId }));
    return () => operation.abort();
  }, [dispatch, id, visitId, state.revision, waitingForPriorMutation]);
  return {
    record: isCurrentVisit ? state.selected : null,
    loading: !isCurrentVisit || ["idle", "pending"].includes(state.detailStatus),
    error: isCurrentVisit ? state.detailError : "",
  };
}

export function useManagers() {
  const [state, setState] = useState({ records: [], loading: true, error: "" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ records: [], loading: true, error: "" });
    listManagers(controller.signal)
      .then((records) => {
        if (!controller.signal.aborted) setState({ records, loading: false, error: "" });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setState({ records: [], loading: false, error: error.message });
      });
    return () => controller.abort();
  }, [attempt]);
  return { ...state, retry: () => setAttempt((value) => value + 1) };
}

export function RentalFields({ values, onChange, managers, creating = false }) {
  return <>
    <TitleFields values={values} onChange={onChange} />
    <label>
      Listing code{creating ? " (optional)" : ""}
      <input name="listingCode" required={!creating} maxLength={64}
        pattern="S6102-R-[1-9][0-9]*" aria-describedby="listing-code-hint"
        value={values.listingCode} onChange={onChange} />
    </label>
    <p className="hint" id="listing-code-hint">
      Use S6102-R- followed by a positive integer.{creating ? " Leave blank to generate a unique code." : ""}
    </p>
    <label>
      Available units
      <input name="availableUnits" type="number" required min="0" max="2147483647" step="1"
        value={values.availableUnits} onChange={onChange} />
    </label>
    <label htmlFor="managerId">Property manager</label>
      <select id="managerId" name="managerId" required disabled={managers.loading || !!managers.error}
        value={values.managerId} onChange={onChange}>
        <option value="">Select a manager</option>
        {managers.records.map((manager) => <option key={manager.id} value={manager.id}>
          {manager.name} — {manager.company} (#{manager.id})
        </option>)}
      </select>
    {managers.loading && <p role="status">Loading property managers…</p>}
    <ErrorNotice error={managers.error} />
    {managers.error && <button type="button" className="secondary" onClick={managers.retry}>Retry managers</button>}
    {!managers.loading && !managers.error && managers.records.length === 0 &&
      <p role="alert">No property managers are available. Add a manager through the property manager API before saving a listing.</p>}
  </>;
}

export function rentalFields(values, creating = false) {
  const listingTitle = values.listingTitle.trim();
  const propertyAddress = values.propertyAddress.trim();
  const listingCode = values.listingCode.trim();
  const availableUnits = Number(values.availableUnits);
  const managerId = Number(values.managerId);
  if (!listingTitle || !propertyAddress) throw new Error("Listing title and property address cannot be blank.");
  if (values.availableUnits === "" || !Number.isSafeInteger(availableUnits) || availableUnits < 0 || availableUnits > 2147483647)
    throw new Error("Available units must be a whole number from 0 to 2147483647.");
  if (!Number.isSafeInteger(managerId) || managerId < 1) throw new Error("Choose a property manager.");
  if ((!creating || listingCode) && !/^S6102-R-[1-9][0-9]*$/.test(listingCode))
    throw new Error("Listing code must be S6102-R- followed by a positive integer.");
  return { listingTitle, propertyAddress, availableUnits, managerId, ...(listingCode ? { listingCode } : {}) };
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

export function FormActions({ pending, disabled = false, label, danger = false }) {
  return (
    <div className="actions">
      <button
        type="submit"
        className={danger ? "danger" : ""}
        disabled={pending || disabled}
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
