"""One JSON event per line, with aware UTC time and process identity."""

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter


def utc_now():
    return datetime.now(timezone.utc)


def event(name: str, **fields):
    record = {
        "timestamp": utc_now().isoformat(),
        "student": "Pragya Apurva",
        "source_commit": os.getenv("HW8_SOURCE_COMMIT", "unrecorded"),
        "pid": os.getpid(),
        "event": name,
        **fields,
    }
    print(json.dumps(record, default=str, sort_keys=True), flush=True)
    return record


def trace_span(trace_id, stage, start, end, duration_ms, *, error=None, **fields):
    if isinstance(trace_id, str) and trace_id:
        event(
            "trace_span",
            trace_id=trace_id,
            correlation_id=trace_id,
            stage=stage,
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            duration_ms=round(duration_ms, 3) if duration_ms is not None else None,
            status="error" if error else "ok",
            error=error,
            **fields,
        )


@contextmanager
def timed_span(trace_id, stage, **fields):
    start, started = utc_now(), perf_counter()
    try:
        yield fields
    except BaseException as exc:
        fields.setdefault("error", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        trace_span(trace_id, stage, start, utc_now(), (perf_counter() - started) * 1000, **fields)
