"""Read-only projections of the shared HW10 evidence files."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any

import streamlit as st

SPAN_FILES = ("tracing/spans.jsonl", "benchmark/spans.jsonl", "evaluation/spans.jsonl")
SCORES_FILE = "evaluation/pipeline_scores.jsonl"
VALIDATION_FILE = "evaluation/judge_validation.json"
EXAMPLES_FILE = "benchmark/examples.json"

SUCCEEDED = {"ok", "success", "succeeded", "completed"}
FAILED = {"error", "failure", "failed", "timeout", "timed_out"}
CACHE_OUTCOMES = {"hit", "miss"}
STAGE_ORDER = (
    "api_request",
    "cache_lookup",
    "inbox",
    "planner",
    "tasks",
    "writer",
    "drafts",
    "reviewer",
    "final",
    "evaluation",
)
STAGE_INDEX = {stage: index for index, stage in enumerate(STAGE_ORDER)}


@st.cache_data(ttl=60, max_entries=32, show_spinner=False)
def parse_file(path: str, version: tuple[int, ...]) -> tuple[list[dict], int]:
    """Return usable rows and a count of invalid JSON lines or objects."""
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    documents = text.splitlines() if file.suffix == ".jsonl" else [text]
    rows = []
    malformed = 0
    for document in documents:
        if not document.strip():
            continue
        try:
            row = json.loads(document)
        except ValueError:
            malformed += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            malformed += 1
    return rows, malformed


class Evidence:
    def __init__(self, root: Path):
        self.root = root
        self.sources: list[str] = []
        self.warnings: list[str] = []

    def rows(self, relative: str) -> list[dict]:
        file = self.root / relative
        try:
            stat = file.stat()
            version = (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            rows, malformed = parse_file(str(file), version)
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError):
            self.warnings.append(f"{relative} could not be read.")
            return []

        self.sources.append(relative)
        if malformed:
            self.warnings.append(f"{relative} · {malformed} malformed record(s) skipped.")
        return rows

    def document(self, relative: str) -> dict:
        rows = self.rows(relative)
        return rows[0] if rows else {}

    def spans(self) -> list["Span"]:
        unique = {}
        for relative in SPAN_FILES:
            for row in self.rows(relative):
                span = Span.from_row(row)
                if span is None:
                    self.warnings.append(
                        f"{relative} · skipped a span without a trace ID or stage."
                    )
                    continue
                # An exported span may also be included in the benchmark bundle.
                unique.setdefault(span.identity, span)
        return list(unique.values())


def text_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return ""


def finite_number(value: Any) -> int | float | None:
    if type(value) in (int, float) and isfinite(value):
        return value
    return None


def utc_time(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            time = datetime.fromisoformat(value)
            if time.tzinfo is not None:
                return time.astimezone(UTC)
        except (ValueError, OverflowError):
            pass
    return None


@dataclass(frozen=True)
class Span:
    trace_id: str
    stage: str
    start: datetime | None
    end: datetime | None
    duration_ms: int | float | None
    status: str
    error: str
    cache_outcome: str
    request_outcome: str
    attempt: int
    span_id: str

    @classmethod
    def from_row(cls, row: dict) -> "Span | None":
        trace_id = row.get("trace_id")
        stage = row.get("stage")
        if not isinstance(trace_id, str) or not trace_id.strip():
            return None
        if not isinstance(stage, str) or not stage.strip():
            return None
        duration = finite_number(row.get("duration_ms"))
        attempt = row.get("attempt")
        return cls(
            trace_id.strip(),
            stage.strip(),
            utc_time(row.get("start_time")),
            utc_time(row.get("end_time")),
            duration if duration is not None and duration >= 0 else None,
            text_value(row.get("status")).lower(),
            text_value(row.get("error")),
            text_value(row.get("cache_outcome")).lower(),
            text_value(row.get("request_outcome")).lower(),
            attempt if type(attempt) is int else 1,
            text_value(row.get("span_id")),
        )

    @property
    def identity(self) -> tuple:
        if self.span_id:
            return (self.trace_id, self.span_id)
        return (self.trace_id, self.stage, self.attempt, self.start, self.end)

    @property
    def api_outcome(self) -> str:
        if self.request_outcome in SUCCEEDED | FAILED:
            return self.request_outcome
        return self.status

    @property
    def completed_request(self) -> bool:
        return (
            self.stage == "api_request"
            and self.end is not None
            and self.api_outcome in SUCCEEDED | FAILED
        )


def completed_requests(spans: list[Span]) -> dict[str, Span]:
    """Select one terminal API span per trace, using the last completion."""
    requests: dict[str, Span] = {}
    for span in sorted(spans, key=lambda span: span.end or datetime.min.replace(tzinfo=UTC)):
        if span.completed_request:
            requests[span.trace_id] = span
    return requests


def cache_outcomes(spans: list[Span], requests: dict[str, Span]) -> dict[str, str]:
    """Use completed cache decisions and the API copy when that span is absent."""
    outcomes = {}
    for span in sorted(spans, key=lambda span: span.end or datetime.min.replace(tzinfo=UTC)):
        if (
            span.stage == "cache_lookup"
            and span.end is not None
            and span.cache_outcome in CACHE_OUTCOMES
        ):
            outcomes[span.trace_id] = span.cache_outcome
    for trace_id, span in requests.items():
        if trace_id not in outcomes and span.cache_outcome in CACHE_OUTCOMES:
            outcomes[trace_id] = span.cache_outcome
    return outcomes


def percentile(values: list[int | float], fraction: float) -> float | None:
    """Linearly interpolate on the sorted observations."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def ordered_trace(spans: list[Span], trace_id: str) -> list[Span]:
    return sorted(
        (span for span in spans if span.trace_id == trace_id),
        key=lambda span: (
            span.stage != "api_request",
            span.start or span.end or datetime.max.replace(tzinfo=UTC),
            STAGE_INDEX.get(span.stage, len(STAGE_ORDER)),
            span.attempt,
        ),
    )
