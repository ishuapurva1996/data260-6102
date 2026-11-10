"""Load and verify the saved Kafka records that make up one evaluation case."""

import fcntl
import json
import math
import os
import signal
import stat
import time
from contextlib import contextmanager
from datetime import UTC, datetime

STAGES = {
    "inbox": ("inbox", None, None),
    "planner": ("tasks", "plan", "plan"),
    "writer": ("drafts", "draft", "draft"),
    "reviewer": ("final", "answer", "final_answer"),
}
MAX_RECORD_BYTES = 1024 * 1024


class EvaluationError(Exception):
    def __init__(self, code, message, *, trace_id=None):
        super().__init__(message)
        self.code = code
        self.trace_id = trace_id


def utc_now():
    return datetime.now(UTC).isoformat(timespec="microseconds")


@contextmanager
def case_deadline(seconds):
    """Bound synchronous loading and inference on the CLI's main thread."""

    def timeout(_signal, _frame):
        raise EvaluationError("case_timeout", "Evaluation exceeded the total deadline")

    previous = signal.signal(signal.SIGALRM, timeout)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def json_value(raw):
    def unique_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate JSON key {key!r}")
            value[key] = item
        return value

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite JSON number")
        return number

    return json.loads(
        raw, object_pairs_hook=unique_keys, parse_float=finite_float, parse_constant=finite_float
    )


def nonempty_text(value):
    return isinstance(value, str) and bool(value.strip())


def valid_facts(value):
    # An explicit empty object or array represents a saved snapshot with no known facts.
    return isinstance(value, (dict, list)) or nonempty_text(value)


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def linked_case(row):
    trace_id = row.get("trace_id")

    def fail(code, message):
        raise EvaluationError(code, message, trace_id=trace_id)

    def require_text(value, name):
        if not nonempty_text(value):
            fail("malformed_evidence", f"{name} must be a nonempty string")
        return value

    for key in ("case_id", "trace_id", "correlation_id", "question"):
        require_text(row.get(key), key)
    if row["correlation_id"] != trace_id:
        fail("conflicting_evidence", "Linked trace_id and correlation_id differ")
    facts = row.get("reference_facts")
    if not valid_facts(facts):
        fail("malformed_evidence", "Missing or invalid reference_facts snapshot")
    messages = row.get("messages")
    if not isinstance(messages, dict):
        fail("malformed_evidence", "messages must contain original stage records")
    missing = STAGES.keys() - messages.keys()
    if missing:
        fail("missing_evidence", f"Missing stage records: {', '.join(sorted(missing))}")

    outputs = {}
    topics = set()
    run_ids = set()
    previous_source = None
    for stage, (topic_suffix, payload_field, result_field) in STAGES.items():
        record = messages[stage]
        if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
            fail("malformed_evidence", f"{stage} must contain a Kafka record and payload")
        topic = require_text(record.get("topic"), f"{stage}.topic")
        prefix, separator, suffix = topic.rpartition("_")
        if not (prefix and separator and suffix == topic_suffix):
            fail("conflicting_evidence", f"{stage} has the wrong Kafka topic")
        topics.add(prefix)
        for field in ("partition", "offset"):
            value = record.get(field)
            if type(value) is not int or value < 0:
                fail("malformed_evidence", f"{stage}.{field} must be a nonnegative integer")

        payload = record["payload"]
        expected_fields = {"correlation_id": trace_id, "question": row["question"]}
        if stage != "inbox":
            expected_fields["from_stage"] = stage
        for field, expected in expected_fields.items():
            if require_text(payload.get(field), f"{stage}.{field}") != expected:
                fail("conflicting_evidence", f"{stage}.{field} disagrees with the linked case")
        run_ids.add(require_text(payload.get("run_id"), f"{stage}.run_id"))
        if canonical_json(payload.get("rental_context")) != canonical_json(facts):
            fail("conflicting_evidence", f"{stage}.rental_context disagrees with reference_facts")
        if previous_source is not None and payload.get("input_source") != previous_source:
            fail("conflicting_evidence", f"{stage} consumed a different Kafka record")
        previous_source = {field: record[field] for field in ("topic", "partition", "offset")}
        for carried_field, earlier in outputs.items():
            if payload.get(carried_field) != earlier:
                fail("conflicting_evidence", f"{stage} did not carry the original {carried_field}")
        if stage == "reviewer" and payload.get("status") != "approved":
            fail("malformed_evidence", "Reviewer message has no approved final answer")
        if payload_field:
            output = require_text(payload.get(payload_field), f"{stage}.{payload_field}")
            if require_text(row.get(result_field), result_field) != output:
                fail(
                    "conflicting_evidence", f"Linked {result_field} differs from the Kafka payload"
                )
            outputs[result_field] = output

    if len(topics) != 1 or len(run_ids) != 1:
        fail("conflicting_evidence", "Kafka topics or pipeline run IDs disagree across stages")
    return {
        **{key: row[key] for key in ("case_id", "trace_id", "correlation_id", "question")},
        "reference_facts": facts,
        **outputs,
        "messages": messages,
    }


def matching_rows(path, selector, identity, expires_at):
    found = []
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise EvaluationError("malformed_evidence", "Linked cases must be a regular file")
        line_number = 0
        while line := source.readline(MAX_RECORD_BYTES + 1):
            line_number += 1
            if time.monotonic() >= expires_at:
                raise EvaluationError("link_timeout", "Deadline exceeded scanning linked cases")
            if len(line) > MAX_RECORD_BYTES:
                raise EvaluationError("malformed_evidence", f"Line {line_number} is too large")
            if not line.strip():
                continue
            try:
                row = json_value(line)
            except (ValueError, RecursionError) as exc:
                raise EvaluationError(
                    "malformed_evidence", f"Invalid linked case JSON at line {line_number}"
                ) from exc
            if not isinstance(row, dict):
                raise EvaluationError("malformed_evidence", f"Line {line_number} is not an object")
            if row.get(selector) == identity or (
                selector == "trace_id" and row.get("correlation_id") == identity
            ):
                found.append(row)
    return found


def replay_key(case):
    return canonical_json(
        {
            **case,
            "messages": {
                stage: {"topic": message["topic"], "payload": message["payload"]}
                for stage, message in case["messages"].items()
                if stage in STAGES
            },
        }
    )


def load_linked_case(path, selector, identity, link_timeout):
    expires_at = time.monotonic() + link_timeout
    missing = EvaluationError("missing_evidence", f"No linked case for {selector}={identity}")
    while True:
        try:
            rows = matching_rows(path, selector, identity, expires_at)
        except FileNotFoundError:
            rows = []
        except OSError as exc:
            raise EvaluationError("malformed_evidence", "Could not read linked cases") from exc

        cases = {}
        incomplete = False
        for row in rows:
            try:
                case = linked_case(row)
            except EvaluationError as exc:
                if exc.code != "missing_evidence":
                    raise
                missing = exc
                incomplete = True
                continue
            cases.setdefault(replay_key(case), case)
        if len(cases) > 1:
            trace_ids = {case["trace_id"] for case in cases.values()}
            raise EvaluationError(
                "conflicting_evidence",
                f"Linked cases disagree for {selector}={identity}",
                trace_id=next(iter(trace_ids)) if len(trace_ids) == 1 else None,
            )
        if cases and not incomplete:
            case = next(iter(cases.values()))
            if selector == "case_id":
                # Check the whole correlation group even when selected by case ID.
                matched = load_linked_case(
                    path, "trace_id", case["trace_id"], expires_at - time.monotonic()
                )
                if replay_key(matched) != replay_key(case):
                    raise EvaluationError(
                        "conflicting_evidence",
                        "Linked case changed while reading its correlation group",
                        trace_id=case["trace_id"],
                    )
                return matched
            return case
        remaining = expires_at - time.monotonic()
        if remaining <= 0:
            raise missing
        time.sleep(min(remaining, 0.1))
        if time.monotonic() >= expires_at:
            raise missing


def append_row(path, row):
    with path.open("a", encoding="utf-8") as destination:
        fcntl.flock(destination, fcntl.LOCK_EX | fcntl.LOCK_NB)
        destination.write(canonical_json(row) + "\n")
