"""Trace Kafka handoffs without changing the payload or receipt fingerprint."""

import json
from datetime import datetime, timedelta
from time import perf_counter

from src.kafka_service.config import DRAFTS, FINAL, INBOX, TASKS
from src.kafka_service.logging import trace_span, utc_now

ENQUEUE_HEADER = "hw10-enqueued-at"
HANDOFFS = {INBOX: "inbox", TASKS: "tasks", DRAFTS: "drafts", FINAL: "final"}


def coordinates(record):
    return {"topic": record.topic, "partition": record.partition, "offset": record.offset}


async def send_traced(producer, topic, payload, key):
    value = json.dumps(payload).encode()
    enqueued, started = utc_now(), perf_counter()
    try:
        record = await producer.send_and_wait(
            topic, value, key=key, headers=[(ENQUEUE_HEADER, enqueued.isoformat().encode())]
        )
    except BaseException as exc:
        trace_span(
            payload.get("correlation_id"),
            HANDOFFS[topic],
            enqueued,
            utc_now(),
            (perf_counter() - started) * 1000,
            operation="publish",
            topic=topic,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    return record, {"enqueue_time": enqueued.isoformat(), "ack_time": utc_now().isoformat()}


def trace_receipt(record, trace_id, received, *, error=None):
    value = dict(getattr(record, "headers", None) or ()).get(ENQUEUE_HEADER)
    if not value:
        return  # Older messages have no measured enqueue time.
    try:
        enqueued = datetime.fromisoformat(value.decode("ascii"))
    except (ValueError, UnicodeError):
        return
    if enqueued.utcoffset() != timedelta(0):
        return
    duration_ms = (received - enqueued).total_seconds() * 1000
    trace_span(
        trace_id,
        HANDOFFS[record.topic],
        enqueued,
        received,
        duration_ms if duration_ms >= 0 else None,
        operation="queue_wait",
        enqueue_time=enqueued.isoformat(),
        receive_time=received.isoformat(),
        error=error or ("Kafka receipt clock precedes enqueue" if duration_ms < 0 else None),
        **coordinates(record),
    )
