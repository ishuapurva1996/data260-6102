import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { deleteRental, fetchRentals } from "../features/rentals/rentalsSlice.js";
import { ErrorNotice } from "../components/forms.jsx";
import { useAuth } from "../auth/AuthContext.jsx";

export default function Home() {
  const { user } = useAuth();
  const canWrite = ["writer", "moderator"].includes(user.role);
  const canDelete = user.role === "moderator";
  const location = useLocation();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [limit, setLimit] = useState(10);
  const [offset, setOffset] = useState(0);
  const dispatch = useDispatch();
  const state = useSelector((store) => store.rentals);
  const loading = ["idle", "pending"].includes(state.listStatus);
  useEffect(() => {
    const operation = dispatch(fetchRentals({ query, limit, offset }));
    return () => operation.abort();
  }, [dispatch, query, limit, offset, attempt, state.revision]);
  useEffect(() => {
    if (state.listStatus === "succeeded" && offset > 0 && offset >= state.total)
      setOffset(Math.max(0, Math.floor((state.total - 1) / limit) * limit));
  }, [state.listStatus, state.total, offset, limit]);
  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR RENTAL DIRECTORY</p>
          <h1>Rental listings</h1>
          <p>Find and manage homes, one listing at a time.</p>
        </div>
        {canWrite && <Link className="button" to="/create">
          Add listing
        </Link>}
      </div>
      {location.state?.notice && (!state.lastMutation || location.state.notice === {
        Added: "Listing added.", Updated: "Listing updated.", Deleted: "Listing deleted.",
      }[state.lastMutation.kind]) && (
        <p className="notice" role="status">
          {location.state.notice}
        </p>
      )}
      {state.lastMutation && (
        <aside className="notice" role="status" data-mutation-result>
          <strong>{state.lastMutation.kind} listing #{state.lastMutation.id}</strong>
          {state.lastMutation.record && <>
            <p>{state.lastMutation.record.listingTitle} · {state.lastMutation.record.propertyAddress}</p>
            <p>{state.lastMutation.record.listingCode} · {state.lastMutation.record.availableUnits} available units · Manager #{state.lastMutation.record.managerId}</p>
            <Link to={`/update?id=${state.lastMutation.id}`}>Update this listing</Link>
          </>}
        </aside>
      )}
      <form
        className="search"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(search.trim());
          setOffset(0);
          setAttempt((value) => value + 1);
        }}
      >
        <label>
          Search listings
          <input
            type="search"
            placeholder="Search title or address"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <button>Search</button>
        {query && (
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setSearch("");
              setQuery("");
              setOffset(0);
            }}
          >
            Clear search
          </button>
        )}
      </form>
      {loading ? (
        <p role="status" className="panel">
          Loading listings…
        </p>
      ) : state.listError ? (
        <div className="panel">
          <ErrorNotice error={state.listError} />
          <button onClick={() => setAttempt((value) => value + 1)}>
            Try again
          </button>
        </div>
      ) : (
        <>
          <p className="result-count">
            {state.total} {state.total === 1 ? "listing" : "listings"}
            {state.total > 0 ? ` · Showing ${offset + 1}–${Math.min(offset + state.records.length, state.total)}` : ""}
            {query ? ` matching “${query}”` : ""}
          </p>
          {state.records.length === 0 ? (
            <div className="panel empty">
              <h2>No listings {query ? "found" : "yet"}</h2>
              <p>
                {query
                  ? "Try another title or address."
                  : "Add your first rental listing to get started."}
              </p>
            </div>
          ) : (
            <div className="listings">
              {state.records.map((record) => (
                <article
                  className="panel rental"
                  key={record.id}
                  data-record-id={record.id}
                >
                  <div className="rental-meta">
                    <span className="badge">{record.propertyType}</span>
                    <span>#{record.id}</span>
                  </div>
                  <h2>{record.listingTitle}</h2>
                  <p className="listing-details">{record.listingCode} · {record.availableUnits} available units · {record.managerId == null ? "No manager assigned" : `Manager #${record.managerId}`}</p>
                  <p className="address">{record.propertyAddress}</p>
                  <p>{record.description}</p>
                  <p className="contact">
                    Landlord Email:{" "}
                    <a href={`mailto:${record.submitterEmail}`}>
                      {record.submitterEmail}
                    </a>
                  </p>
                  <div className="actions">
                    {canWrite && <Link to={`/update?id=${record.id}`}>Update</Link>}
                    {canDelete && <button className="danger" disabled={state.mutations[`record:${record.id}`]?.status === "pending"}
                      onClick={() => dispatch(deleteRental(record.id))}>
                      {state.mutations[`record:${record.id}`]?.status === "pending" ? "Deleting…" : "Delete"}
                    </button>}
                    {canDelete && <Link className="danger-link" to={`/delete?id=${record.id}`}>Review deletion</Link>}
                  </div>
                  <ErrorNotice error={state.mutations[`record:${record.id}`]?.error} />
                </article>
              ))}
            </div>
          )}
          <nav className="pagination" aria-label="Listing pages">
            <button className="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous page</button>
            <span>Page {Math.floor(offset / limit) + 1} of {Math.max(1, Math.ceil(state.total / limit))}</span>
            <button className="secondary" disabled={offset + limit >= state.total} onClick={() => setOffset(offset + limit)}>Next page</button>
            <label>Listings per page
              <select value={limit} onChange={(event) => { setLimit(Number(event.target.value)); setOffset(0); }}>
                {[5, 10, 25, 50].map((size) => <option key={size} value={size}>{size}</option>)}
              </select>
            </label>
          </nav>
        </>
      )}
    </section>
  );
}
