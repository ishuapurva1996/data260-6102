"""Export selected HW10 traces and the original messages on each completed miss."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

HANDOFFS = ("inbox", "tasks", "drafts", "final")
AGENTS = ("planner", "writer", "reviewer")
EVENTS = {"trace_span", "question_sent", "output_published", "final_received"}


def location(row, prefix=""):
    return tuple(row[prefix + field] for field in ("topic", "partition", "offset"))


def read_events(log_dir, trace_ids):
    events = defaultdict(list)
    for path in sorted(log_dir.glob("*.log")):
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.startswith("{"):
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # A process may still be writing its final line.
                trace_id = row.get("correlation_id")
                if row.get("event") in EVENTS and isinstance(trace_id, str):
                    if trace_id in trace_ids:
                        events[trace_id].append(row)
    return events


def publications(rows):
    found = {}
    for row in rows:
        name = row["event"]
        if name == "question_sent":
            broker = location(row)
            payload = row["payload"]
        elif name == "output_published":
            broker = location(row, "output_")
            payload = row["output"]
        else:
            continue
        message = dict(zip(("topic", "partition", "offset"), broker))
        message.update(payload=payload, enqueue_time=row["enqueue_time"], ack_time=row["ack_time"])
        if found.setdefault(broker, message) != message:
            raise ValueError(f"Conflicting publications at {broker}")
    return found


def link_case(rows, published, spans, trace_id, case_id):
    deliveries = {
        (location(row), json.dumps(row["final"], sort_keys=True))
        for row in rows
        if row["event"] == "final_received"
    }
    if len(deliveries) != 1:
        raise ValueError(f"{trace_id}: expected one delivered final")
    broker, delivered = next(iter(deliveries))
    messages = {}
    for handoff, sender in zip(reversed(HANDOFFS), (*reversed(AGENTS), "inbox"), strict=True):
        message = published.get(broker)
        if message is None or broker[0] != f"s6102_{handoff}":
            raise ValueError(f"{trace_id}: missing {handoff} publication at {broker}")
        payload = message["payload"]
        if payload.get("correlation_id") != trace_id:
            raise ValueError(f"{trace_id}: {handoff} publication has a different correlation_id")
        receives = [
            span["receive_time"]
            for span in spans
            if span["stage"] == handoff
            and span.get("operation") == "queue_wait"
            and span["status"] == "ok"
            and location(span) == broker
            and span["enqueue_time"] == message["enqueue_time"]
        ]
        if not receives:
            raise ValueError(f"{trace_id}: missing matching {handoff} receipt at {broker}")
        messages[sender] = {**message, "receive_time": min(receives)}
        if sender != "inbox":
            if payload.get("from_stage") != sender:
                raise ValueError(f"{trace_id}: expected {sender} output at {broker}")
            broker = location(payload["input_source"])

    request = messages["inbox"]["payload"]
    plan = messages["planner"]["payload"]["plan"]
    draft = messages["writer"]["payload"]["draft"]
    final = messages["reviewer"]["payload"]
    if (
        json.loads(delivered) != final
        or final.get("status") != "approved"
        or any(
            not isinstance(value, str) or not value.strip()
            for value in (request["question"], plan, draft, final["answer"])
        )
        or not isinstance(request["rental_context"], dict)
        or any(
            message["payload"].get(field) != request[field]
            for message in messages.values()
            for field in ("question", "rental_context", "run_id")
        )
        or messages["writer"]["payload"].get("plan") != plan
        or final.get("plan") != plan
        or final.get("draft") != draft
    ):
        raise ValueError(f"{trace_id}: incomplete or inconsistent delivered messages")
    return {
        "case_id": case_id,
        "trace_id": trace_id,
        "correlation_id": trace_id,
        "question": request["question"],
        "reference_facts": request["rental_context"],
        "plan": plan,
        "draft": draft,
        "final_answer": final["answer"],
        "messages": messages,
    }


def extract(log_dir, cases):
    events = read_events(log_dir, cases)
    all_spans, linked = [], []
    for trace_id, case_id in cases.items():
        rows = events[trace_id]
        published = publications(rows)
        spans = []
        seen = set()
        for row in rows:
            if row["event"] != "trace_span" or row["trace_id"] != trace_id:
                continue
            identity = json.dumps(row, sort_keys=True)
            if identity in seen:
                continue
            seen.add(identity)
            span = dict(row)
            if span.get("operation") == "queue_wait":
                message = published.get(location(span))
                if message and message["enqueue_time"] == span["enqueue_time"]:
                    span["ack_time"] = message["ack_time"]
            spans.append(span)
        api = [span for span in spans if span["stage"] == "api_request"]
        if len(api) != 1:
            raise ValueError(f"{trace_id}: expected one completed API span, found {len(api)}")
        if api[0]["status"] == "ok" and api[0]["cache_outcome"] == "miss":
            linked.append(link_case(rows, published, spans, trace_id, case_id))
        all_spans.extend(sorted(spans, key=lambda span: span["start_time"]))
    return all_spans, linked


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--trace-id", action="append", required=True)
    parser.add_argument("--case-id", help="Case ID for a single selected trace")
    args = parser.parse_args()
    if args.case_id and len(args.trace_id) != 1:
        parser.error("--case-id requires exactly one --trace-id")
    cases = {trace_id: args.case_id or f"case-{trace_id}" for trace_id in args.trace_id}
    try:
        spans, linked = extract(args.log_dir, cases)
    except (KeyError, TypeError, ValueError) as exc:
        parser.exit(1, f"Trace export failed: {exc}\n")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "spans.jsonl", spans)
    write_jsonl(args.output_dir / "linked_cases.jsonl", linked)
    print(f"Exported {len(spans)} spans and {len(linked)} linked cases.")


if __name__ == "__main__":
    main()
