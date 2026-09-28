import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { rentals } from "../api/client.js";
import { ErrorNotice } from "../components/forms.jsx";

export default function Home() {
  const location = useLocation();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ loading: true, records: [] });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true, records: [] });
    rentals
      .list(query, controller.signal)
      .then((records) => {
        if (!controller.signal.aborted) setState({ records, loading: false });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ records: [], loading: false, error: error.message });
      });
    return () => controller.abort();
  }, [query, attempt]);
  const highest = state.records.reduce(
    (max, row) => (row.id > (max?.id || 0) ? row : max),
    null,
  );
  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR RENTAL DIRECTORY</p>
          <h1>Rental listings</h1>
          <p>Find and manage homes, one listing at a time.</p>
        </div>
        <Link className="button" to="/create">
          Add listing
        </Link>
      </div>
      {location.state?.notice && (
        <p className="notice" role="status">
          {location.state.notice}
        </p>
      )}
      <form
        className="search"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(search.trim());
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
            }}
          >
            Clear search
          </button>
        )}
      </form>
      {state.loading ? (
        <p role="status" className="panel">
          Loading listings…
        </p>
      ) : state.error ? (
        <div className="panel">
          <ErrorNotice error={state.error} />
          <button onClick={() => setAttempt((value) => value + 1)}>
            Try again
          </button>
        </div>
      ) : (
        <>
          <p className="result-count">
            {state.records.length}{" "}
            {state.records.length === 1 ? "listing" : "listings"}
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
                  <p className="address">{record.propertyAddress}</p>
                  <p>{record.description}</p>
                  <p className="contact">
                    Landlord Email:{" "}
                    <a href={`mailto:${record.submitterEmail}`}>
                      {record.submitterEmail}
                    </a>
                  </p>
                  <div className="actions">
                    <Link to={`/update?id=${record.id}`}>Update</Link>
                    <Link
                      className="danger-link"
                      to={`/delete?id=${record.id}`}
                    >
                      Delete
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          )}
          {!query && highest && (
            <div className="utility">
              <Link className="danger-link" to={`/delete?id=${highest.id}`}>
                Delete highest ID (#{highest.id})
              </Link>
              <span>Review the listing before deleting.</span>
            </div>
          )}
        </>
      )}
    </section>
  );
}
