"""Streamlit operations dashboard for the rental assistant's saved HW10 evidence."""

import os
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import streamlit as st
from dashboard_evidence import (
    EXAMPLES_FILE,
    FAILED,
    SCORES_FILE,
    VALIDATION_FILE,
    Evidence,
    cache_outcomes,
    completed_requests,
    finite_number,
    ordered_trace,
    parse_file,
    percentile,
    text_value,
)

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_ROOT = ROOT / "tests/fixtures/hw10_dashboard_synthetic"
EMPTY = "—"
WINDOWS = {"Latest hour": timedelta(hours=1), "Latest 24 hours": timedelta(days=1)}


def utc_label(value):
    return (
        value.isoformat(sep=" ", timespec="milliseconds").replace("+00:00", "Z") if value else EMPTY
    )


def metrics(items):
    for column, (label, value) in zip(st.columns(len(items)), items):
        column.metric(label, value)


def formatted(value, spec, suffix=""):
    number = finite_number(value)
    return f"{number:{spec}}{suffix}" if number is not None else EMPTY


def window_for(requests):
    ends = [span.end for span in requests.values()]
    latest = max(ends, default=None)
    choice = st.selectbox(
        "Completion window",
        ["Latest 24 hours", "Latest hour", "All evidence", "Custom UTC dates"],
        key="summary_window",
        help="Relative windows end at the newest saved API completion.",
    )
    if choice == "Custom UTC dates":
        day = (latest or datetime.now(UTC)).date()
        dates = st.date_input("Start and end dates (UTC, inclusive)", (day, day))
        if len(dates) != 2:
            st.info("Select both dates to set a completion window.")
            return None
        start = datetime.combine(dates[0], time.min, UTC)
        end = datetime.combine(dates[1], time.max, UTC)
    elif latest is None:
        start = end = None
    else:
        start = latest - WINDOWS[choice] if choice in WINDOWS else min(ends)
        end = latest
    st.caption(
        f"Window (UTC) · {utc_label(start)} to {utc_label(end)}"
        if end
        else "Window (UTC) · No saved API completions to set the bounds."
    )
    return start, end


def render_summary(evidence):
    spans = evidence.spans()
    requests = completed_requests(spans)
    window = window_for(requests)
    if window is None:
        return
    start, end = window
    selected = {
        trace_id: span
        for trace_id, span in requests.items()
        if start is not None and start <= span.end <= end
    }
    outcomes = cache_outcomes(spans, selected)
    hits = sum(outcomes.get(trace_id) == "hit" for trace_id in selected)
    misses = sum(outcomes.get(trace_id) == "miss" for trace_id in selected)
    errors = sum(span.api_outcome in FAILED for span in selected.values())
    sources = ", ".join(path for path in evidence.sources if path != "evaluation/spans.jsonl")
    st.caption(f"Source for all metrics · {sources or 'No saved API or cache spans'}")
    if not selected:
        st.info("No completed requests in this window.")

    metrics(
        [
            ("Completed requests", f"{len(selected):,}"),
            ("Cache hits", f"{hits:,}"),
            ("Cache misses", f"{misses:,}"),
        ]
    )
    metrics(
        [
            ("Cache hit rate", f"{hits / (hits + misses):.1%}" if hits + misses else EMPTY),
            ("Request error rate", f"{errors / len(selected):.1%}" if selected else EMPTY),
        ]
    )
    st.caption(
        f"{hits + misses:,} known cache decisions · {len(selected) - hits - misses:,} without a decision"
        f" · {errors:,} API failures. Hit rate uses known decisions. "
        "Error rate uses all completed requests."
    )

    st.subheader("Response latency")
    api_ms = [span.duration_ms for span in selected.values() if span.duration_ms is not None]
    hit_ms = [
        span.duration_ms
        for trace_id, span in selected.items()
        if outcomes.get(trace_id) == "hit" and span.duration_ms is not None
    ]
    metrics(
        [
            ("API latency (p50)", formatted(percentile(api_ms, 0.5), ",.0f", " ms")),
            ("API latency (p95)", formatted(percentile(api_ms, 0.95), ",.0f", " ms")),
        ]
    )
    metrics(
        [
            ("Cache-hit latency (p50)", formatted(percentile(hit_ms, 0.5), ",.0f", " ms")),
            ("Cache-hit latency (p95)", formatted(percentile(hit_ms, 0.95), ",.0f", " ms")),
        ]
    )
    st.caption(
        f"API ingress to response · {len(api_ms):,} saved API durations "
        f"and {len(hit_ms):,} saved hit durations. "
        "Cache-hit latency uses the whole API request for hits."
    )


def render_pipeline(evidence):
    st.subheader("Pipeline scores by case")
    cases = [
        row
        for row in evidence.rows(SCORES_FILE)
        if text_value(row.get("case_id")) and text_value(row.get("trace_id"))
    ]
    if not cases:
        st.info("No saved pipeline scores are available.")
        return
    case = cases[
        st.selectbox(
            "Scored case",
            range(len(cases)),
            format_func=lambda i: f"{cases[i]['case_id']} · {cases[i]['trace_id']}",
        )
    ]
    st.caption(f"Source · {SCORES_FILE}")
    if question := text_value(case.get("question")):
        st.text(question)

    scores = case.get("scores")
    scores = scores if isinstance(scores, dict) else {}
    stages = []
    for stage, criterion in [
        ("Planner", "Plan quality"),
        ("Writer", "Draft helpfulness"),
        ("Reviewer", "Final answer helpfulness"),
    ]:
        result = scores.get(stage.lower())
        result = result if isinstance(result, dict) else {}
        score = finite_number(result.get("score"))
        stages.append(
            {
                "Stage": stage,
                "Criterion": criterion,
                "Score / 5": score if score is not None and 1 <= score <= 5 else None,
                "Reason": text_value(result.get("reason")) or EMPTY,
            }
        )
    st.dataframe(stages, hide_index=True, width="stretch")

    st.subheader("Draft and final")
    writer, reviewer = (stage["Score / 5"] for stage in stages[1:])
    metrics(
        [
            ("Writer draft", formatted(writer, "g", " / 5")),
            ("Reviewer final", formatted(reviewer, "g", " / 5")),
            ("Final − draft", formatted(case.get("final_minus_draft"), "+g")),
        ]
    )
    st.text(text_value(case.get("interpretation")) or "No interpretation was saved for this case.")
    for label, key in (("Writer draft", "draft"), ("Reviewer final answer", "final")):
        with st.expander(label):
            st.text(text_value(case.get(key)) or "No answer text was saved.")


def render_validation(evidence):
    st.subheader("Judge validation")
    validation = evidence.document(VALIDATION_FILE)
    if not validation:
        st.info("No saved judge-validation results are available.")
        return

    st.caption(f"Source · {VALIDATION_FILE} · Human reference vs. judge pass 1")
    if validation.get("status") == "incomplete":
        st.warning(
            "Judge validation is incomplete. Comparison and repeatability require three complete passes."
        )
        return
    spearman = formatted(validation.get("spearman"), ".3f")
    if "spearman" in validation and validation["spearman"] is None:
        spearman = "Undefined"
    metrics(
        [
            ("Spearman correlation", spearman),
            (
                "Mean absolute difference",
                formatted(validation.get("mean_absolute_difference"), ".2f", " pts"),
            ),
        ]
    )

    repeatability = validation.get("repeatability")
    if not isinstance(repeatability, dict):
        st.info("No saved repeatability results are available.")
        return

    count = validation.get("case_count")
    changed = repeatability.get("changed_count")
    rate = repeatability.get("changed_rate")
    change_count = f"{changed} / {count}" if type(changed) is int and type(count) is int else EMPTY
    if finite_number(rate) is not None:
        change_count += f" ({rate:.1%})"
    st.markdown("**Repeatability across three judge passes**")
    metrics(
        [
            ("Cases with score changes", change_count),
            ("Mean score change", formatted(repeatability.get("mean_score_change"), ".2f", " pts")),
            ("Max score change", formatted(repeatability.get("max_score_change"), ".2f", " pts")),
        ]
    )
    st.caption(
        "For each case, score change is the highest score minus the lowest across the three passes."
    )
    if interpretation := text_value(validation.get("interpretation")):
        st.text(interpretation)


def render_trace(evidence):
    spans = evidence.spans()
    examples = evidence.document(EXAMPLES_FILE)
    choices = [
        (label, trace_id)
        for key, label in (
            ("hit", "Cache hit"),
            ("miss", "Successful miss"),
            ("failure", "Failed request"),
        )
        if (trace_id := examples.get(key)) and isinstance(trace_id, str)
    ]
    if choices:
        st.caption("Saved trace examples")
        for column, (label, trace_id) in zip(st.columns(len(choices)), choices):
            column.button(label, on_click=st.session_state.update, kwargs={"trace_id": trace_id})
    trace_id = st.text_input("Trace ID", key="trace_id", placeholder="Paste a trace_id").strip()
    if not trace_id:
        st.info("Enter a trace ID or choose a saved example to inspect its journey.")
        return
    trace = ordered_trace(spans, trace_id)
    if not trace:
        st.warning("No saved spans match this trace ID.")
        return

    requests = completed_requests(trace)
    request = requests.get(trace_id)
    cache = cache_outcomes(trace, requests).get(trace_id)
    failed_stages = [
        span
        for span in trace
        if span.status in FAILED and span.stage not in {"api_request", "evaluation"}
    ]
    if request is None:
        st.warning("Incomplete trace · no completed API span.")
    elif request.api_outcome in FAILED:
        failure = failed_stages[-1] if failed_stages else request
        message = (
            f"Failed request · {failure.stage} recorded an error · cache {cache or 'unknown'}."
        )
        if failure.error:
            message += f"\n\n{failure.error}"
        st.error(message)
    elif cache == "hit":
        st.success("Cache hit · the API returned a saved answer.")
    elif cache == "miss":
        st.info("Successful cache miss · the API returned a new answer.")
    else:
        st.warning("Completed request · cache decision unavailable.")

    expected = {"api_request", "cache_lookup"}
    if request and request.api_outcome not in FAILED and cache == "miss":
        expected.update(("inbox", "planner", "tasks", "writer", "drafts", "reviewer", "final"))
    absent = expected - {span.stage for span in trace if span.end is not None}
    if absent or any(span.start is None or span.end is None for span in trace):
        st.caption(
            f"Incomplete span evidence · missing closed stages: {', '.join(sorted(absent)) or 'none'}."
        )

    st.caption(
        f"Source · {', '.join(path for path in evidence.sources if path.endswith('/spans.jsonl'))}"
    )
    st.dataframe(
        [
            {
                "Stage": span.stage,
                "Start (UTC)": utc_label(span.start),
                "End (UTC)": utc_label(span.end),
                "Duration (ms)": span.duration_ms,
                "Status": span.status or EMPTY,
                "Cache": span.cache_outcome or EMPTY,
                "Attempt": span.attempt,
                "Error": span.error or EMPTY,
            }
            for span in trace
        ],
        hide_index=True,
        width="stretch",
    )


def main():
    st.set_page_config(page_title="Rental Pipeline | HW10", layout="wide")
    root_setting = os.getenv("HW10_EVIDENCE_ROOT")
    root = Path(root_setting).expanduser().resolve() if root_setting else SYNTHETIC_ROOT
    synthetic = root == SYNTHETIC_ROOT or (root / "SYNTHETIC").is_file()
    evidence = Evidence(root)

    with st.sidebar:
        st.header("Rental Pipeline")
        st.caption("DATA 260 · Homework 10")
        page = st.radio("Pages", ("Summary", "Evaluation", "Trace Lookup"), key="page")
        st.divider()
        st.caption("Evidence directory")
        st.code(str(root), language=None, wrap_lines=True)
        st.button("Refresh evidence", key="refresh_evidence", on_click=parse_file.clear)
        st.caption("File changes are picked up on the next interaction or refresh.")

    st.title(page)
    if synthetic:
        st.warning("Synthetic evidence · Illustrative examples for dashboard testing.")
    else:
        st.caption("Recorded evidence · Saved files")
    if not root.is_dir():
        st.warning("The evidence directory is unavailable.")
    if page == "Summary":
        render_summary(evidence)
    elif page == "Evaluation":
        render_pipeline(evidence)
        render_validation(evidence)
    else:
        render_trace(evidence)

    for warning in evidence.warnings:
        st.warning(warning)


if __name__ == "__main__":
    main()
