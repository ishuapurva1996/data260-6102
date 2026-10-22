import React, { useEffect, useRef, useState } from "react";
import { request } from "../api/client.js";
import { ErrorNotice } from "../components/forms.jsx";
import "../bikeshare.css";
import { useBikeRun } from "../BikeRunContext.jsx";

const ACTIVE = ["submitting", "queued", "running"];
const POLL_LIMIT_MS = 12 * 60 * 1000;

function json(value) {
  return value === undefined ? "Not reported" : JSON.stringify(value, null, 2);
}

function money(value) {
  if (value === undefined || value === null) return "—";
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString("en-US", { style: "currency", currency: "USD" })
    : String(value);
}

function timestamp(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime()) ? date.toISOString() : "Not reported";
}

function ToolTimeline({ events, active }) {
  const calls = [];
  for (const event of events) {
    if (event.event === "tool_request") {
      calls.push({ ...event, hasResult: false });
    } else if (event.event === "tool_rejected") {
      calls.push({ ...event, hasResult: true, rejected: true });
    } else if (event.event === "tool_result") {
      const call = calls.find((item) => item.call_id === event.call_id && !item.hasResult);
      if (call) {
        call.result = event.result;
        call.hasResult = true;
      } else {
        calls.push({ ...event, inputs: undefined, hasResult: true });
      }
    }
  }
  return (
    <section className="panel bike-timeline" aria-labelledby="bike-timeline-title">
      <h2 id="bike-timeline-title">Tool timeline</h2>
      <p className="bike-muted">Actual requests and observations from this run.</p>
      {!calls.length ? (
        <p className="bike-empty">{active ? "Waiting for the first tool request…" : "Run a comparison to see its tool calls here."}</p>
      ) : (
        <ol className="bike-calls">
          {calls.map((call, index) => (
            <li key={`${call.call_id}-${index}`} className={call.result?.success === false ? "bike-call-error" : ""}>
              <div className="bike-call-heading">
                <h3>{index + 1}. {call.name}</h3>
                <span className="bike-chip">{call.rejected ? "Rejected proposal" : call.hasResult ? (call.result?.success === false ? "Error" : "Observed") : "Requested"}</span>
              </div>
              <p className="bike-call-id">Call ID: {call.call_id || "Not reported"}</p>
              <h4>Input</h4>
              <pre>{json(call.inputs)}</pre>
              <h4>Observation</h4>
              {call.hasResult ? <pre>{json(call.result)}</pre> : <p className="bike-muted">No observation received yet.</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Metrics({ metrics = {} }) {
  return (
    <dl className="bike-metrics" aria-label="Run metrics">
      <div><dt>Steps</dt><dd>{metrics.steps ?? "—"}</dd></div>
      <div><dt>Total time</dt><dd>{Number.isFinite(metrics.latency_ms) ? `${(metrics.latency_ms / 1000).toFixed(1)} s` : "—"}</dd></div>
      <div><dt>Stop reason</dt><dd>{metrics.stop_reason || "—"}</dd></div>
      <div><dt>Model requests</dt><dd>{metrics.model_requests ?? "—"}</dd></div>
      <div><dt>Tool calls</dt><dd>{metrics.tool_calls ?? "—"}</dd></div>
      <div><dt>Tokens</dt><dd>{metrics.total_tokens ?? "Not reported"}</dd></div>
    </dl>
  );
}

function Result({ result }) {
  if (!result) return null;
  const accepted = result.verification?.passed === true &&
    ["Buy Monthly Membership", "Pay Per Ride/Minute"].includes(result.decision);
  const breakEven = result.break_even || {};
  const example = result.per_account?.[0];
  return (
    <div className="bike-results">
      <section className="panel" aria-labelledby="bike-result-title">
        <p className="eyebrow">{accepted ? "VERIFIED RECOMMENDATION" : "VERIFICATION DID NOT PASS"}</p>
        <h2 id="bike-result-title">{accepted ? result.decision : "No accepted recommendation"}</h2>
        {accepted ? <p className="bike-justification">{result.justification}</p> : (
          <div className="notice error">
            <p>The agent’s answer did not pass the independent checks.</p>
            {result.verification?.failures?.length > 0 && <pre>{json(result.verification.failures)}</pre>}
          </div>
        )}
        <Metrics metrics={result.metrics} />
        <p className="bike-muted">{result.row_count ?? "—"} trip rows · {result.account_count ?? "—"} scenario accounts · USD</p>
        <p className="bike-muted">Coverage: {result.coverage_start || "—"} to {result.coverage_end || "—"}. Account assignments are hypothetical.</p>
        <h3>Deterministic cost comparison</h3>
        <dl className="bike-costs">
          <div><dt>Pay per ride/minute</dt><dd>{money(result.pay_per_use_total)}</dd></div>
          <div className="bike-cost-total"><dt>Membership total</dt><dd>{money(result.membership_total)}</dd></div>
          <div><dt>Membership fees</dt><dd>{money(result.membership_fee_total)}</dd></div>
          <div><dt>Membership ride charges</dt><dd>{money(result.membership_residual_total)}</dd></div>
          <div className="bike-savings"><dt>Savings with membership</dt><dd>{money(result.savings)}</dd></div>
        </dl>
        {example && <p className="bike-muted">Example assumed account {example.account_id}: {example.ride_count} rides; pay per use {money(example.pay_per_use)}, membership {money(example.membership_total)}, including its own {money(example.membership_fee)} fee.</p>}
        {!accepted && result.model_answer && <details><summary>Unverified agent answer</summary><pre>{typeof result.model_answer === "string" ? result.model_answer : json(result.model_answer)}</pre></details>}
      </section>

      <section className="panel" aria-labelledby="bike-weekly-title">
        <h2 id="bike-weekly-title">Weekly breakdown</h2>
        <div className="bike-table-scroll" tabIndex={0} role="region" aria-label="Weekly cost table">
          <table className="bike-table">
            <caption>Ride costs and allocated membership fees by week</caption>
            <thead><tr><th scope="col">Week starting</th><th scope="col">Rides</th><th scope="col">Avg. min</th><th scope="col">Pay per use</th><th scope="col">Member rides</th><th scope="col">Allocated fee</th><th scope="col">Member total</th></tr></thead>
            <tbody>{(result.weekly || []).map((week) => <tr key={week.week_start}>
              <th scope="row">{week.week_start}</th><td>{week.ride_count}</td><td>{week.average_duration_minutes}</td>
              <td>{money(week.pay_per_use)}</td><td>{money(week.member_residual)}</td><td>{money(week.allocated_membership_fee)}</td><td>{money(week.membership_total)}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="bike-break-even-title">
        <h2 id="bike-break-even-title">Break-even usage</h2>
        <dl className="bike-facts">
          <div><dt>Rides at the sample mix</dt><dd>{breakEven.rides_at_sample_mix ?? "Not reported"}</dd></div>
          <div><dt>Minutes at the sample mix</dt><dd>{breakEven.minutes_at_sample_mix ?? "Not reported"}</dd></div>
          <div><dt>Actual rides per account</dt><dd>{typeof breakEven.actual_rides_per_account === "object" ? json(breakEven.actual_rides_per_account) : breakEven.actual_rides_per_account ?? (breakEven.min !== undefined ? `${breakEven.min}–${breakEven.max}` : "Not reported")}</dd></div>
          <div><dt>Average saving per ride</dt><dd>{money(breakEven.average_saving_per_ride)}</dd></div>
        </dl>
        {breakEven.method && <p className="bike-muted">{breakEven.method}</p>}
        <h3>Account and coverage assumptions</h3>
        <ul className="bike-assumptions">{(result.assumptions || []).map((assumption, index) => <li key={index}>{assumption}</li>)}</ul>
      </section>

      <section className="panel" aria-labelledby="bike-citations-title">
        <h2 id="bike-citations-title">Captured pricing sources</h2>
        <ol className="bike-citations">{(result.citations || []).map((citation, index) => (
          <li key={`${citation.url}-${index}`}>
            <a href={/^https?:\/\//i.test(citation.url) ? citation.url : undefined} target="_blank" rel="noreferrer">{citation.url}</a>
            <p>Captured: <time dateTime={citation.captured_at}>{timestamp(citation.captured_at)}</time></p>
            <blockquote>{citation.excerpt}</blockquote>
            <p className="bike-hash">SHA-256: {citation.sha256}</p>
          </li>
        ))}</ol>
      </section>
    </div>
  );
}

export default function BikeShare() {
  const [file, setFile] = useState(null);
  const [pricingUrl, setPricingUrl] = useState("https://capitalbikeshare.com/pricing");
  const [runId, setRunId] = useBikeRun();
  const [status, setStatus] = useState("idle");
  const [events, setEvents] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const mounted = useRef(false);
  const locked = useRef(false);
  const submission = useRef(null);
  const active = ACTIVE.includes(status);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      submission.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!runId) return;
    locked.current = true;
    setStatus("running");
    const controller = new AbortController();
    const deadline = Date.now() + POLL_LIMIT_MS;
    let timer;
    async function poll() {
      try {
        const run = await request(`/bikeshare/runs/${encodeURIComponent(runId)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setError(run.error || "");
        setEvents(Array.isArray(run.events) ? run.events : []);
        setResult(run.result || null);
        if (["completed", "failed"].includes(run.status)) {
          setStatus(run.status);
          setError(run.error || "");
          locked.current = false;
        } else if (Date.now() >= deadline) {
          setStatus("poll_timeout");
          setError("The twelve-minute display limit was reached. The server may still be finishing this run; no additional run was submitted.");
          locked.current = false;
        } else if (["queued", "running"].includes(run.status)) {
          setStatus(run.status);
          timer = setTimeout(poll, 1000);
        } else {
          throw new Error("The server returned an unknown run status.");
        }
      } catch (failure) {
        if (controller.signal.aborted) return;
        const transient = !failure.status || failure.status === 429 || failure.status >= 500;
        if (transient && Date.now() < deadline) {
          setError("Status refresh failed. Retrying the existing run; no new comparison was submitted.");
          timer = setTimeout(poll, 3000);
          return;
        }
        setError(failure.message);
        setStatus(Date.now() >= deadline ? "poll_timeout" : "failed");
        locked.current = false;
      }
    }
    poll();
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [runId]);

  async function submit(event) {
    event.preventDefault();
    if (locked.current) return;
    if (!file) {
      setError("Choose a trip CSV before running the comparison.");
      return;
    }
    locked.current = true;
    const controller = new AbortController();
    submission.current = controller;
    setStatus("submitting");
    setError("");
    setEvents([]);
    setResult(null);
    setRunId(null);
    const body = new FormData();
    body.append("file", file);
    body.append("pricing_url", pricingUrl.trim());
    try {
      const run = await request("/bikeshare/runs", { method: "POST", body, signal: controller.signal });
      if (!mounted.current || controller.signal.aborted) return;
      if (!run.run_id || !["queued", "running"].includes(run.status)) throw new Error("The server did not return a valid run ID and status.");
      setRunId(run.run_id);
      setStatus(run.status);
    } catch (failure) {
      if (!mounted.current || controller.signal.aborted) return;
      setError(failure.message);
      setStatus("failed");
      locked.current = false;
    }
  }

  return (
    <section className="bike-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Pragya Apurva · DATA 260 · s6102</p>
          <h1>Bike-share cost comparison</h1>
          <p>Compare a 30-day membership with paying for each ride using genuine trip rows and captured official prices.</p>
        </div>
      </div>
      <section className="panel bike-input-panel" aria-labelledby="bike-input-title">
        <h2 id="bike-input-title">Run a scenario</h2>
        <p className="bike-muted">Each account needs its own membership. Hypothetical account assignments must be declared as scenario assumptions; citywide trips are not one rider’s history.</p>
        <form onSubmit={submit}>
          <fieldset disabled={active} className="bike-inputs">
            <div>
              <label htmlFor="bike-csv">Trip CSV
                <input id="bike-csv" name="file" type="file" accept=".csv,text/csv" required aria-describedby="bike-csv-hint" onChange={(event) => setFile(event.target.files?.[0] || null)} />
              </label>
              <p id="bike-csv-hint" className="hint">Use at least 500 genuine rows, with scenario_account_id, coverage_start, coverage_end, and scenario_account_assumption columns. Preserve source-row provenance.</p>
            </div>
            <div>
              <label htmlFor="bike-pricing">Official pricing URL
                <input id="bike-pricing" name="pricing_url" type="url" required value={pricingUrl} onChange={(event) => setPricingUrl(event.target.value)} />
              </label>
              <p className="hint">The run captures the policy text, access time, and exact snapshot hash.</p>
            </div>
            <button type="submit">{active ? "Running…" : "Run"}</button>
          </fieldset>
        </form>
      </section>
      <div className="bike-run-status" role="status" aria-live="polite">
        {status !== "idle" && <><strong>{({ submitting: "Uploading scenario", queued: "Queued", running: "Agent running", completed: "Run completed", failed: "Run stopped", poll_timeout: "Display limit reached" })[status]}</strong>{runId && <span>Run {runId}</span>}</>}
      </div>
      <ErrorNotice error={error} />
      <div className="bike-workspace" aria-busy={active}>
        <ToolTimeline events={events} active={active} />
        {result ? <Result result={result} /> : <section className="panel bike-awaiting"><h2>Comparison results</h2><p>{active ? "Costs, the verified decision, weekly breakdown, and captured citations will appear when the run finishes." : "Choose a scenario CSV and official pricing page to begin."}</p></section>}
      </div>
    </section>
  );
}
