"""Verify a live miss/hit pair or collect 20 Writer drafts on an owned HW10 stack."""

import argparse
import csv
import json
import os
from pathlib import Path

import httpx

from scripts.hw10.export_traces import AGENTS, HANDOFFS, extract
from src.hw09.semantic_cache import CacheSettings, SemanticCache

ROOT = Path(__file__).resolve().parents[2]
SMOKE = "How many units are available at S6102-R-9101?"
QUESTIONS = (
    "How many units are currently available at S6102-R-9102?",
    "What is the advertised title of S6102-R-9103?",
    "Is S6102-R-9104 listed as a townhouse?",
    "Give me the property type and number of available units at S6102-R-9105.",
    "Does S6102-R-9106 have at least two units available?",
    "What is the listing title and property type for S6102-R-9107?",
    "How many total units are available across S6102-R-9108 and S6102-R-9109?",
    "Which has more available units, S6102-R-9110 or S6102-R-9101, and by how many?",
    "Which of S6102-R-9102 and S6102-R-9103 is a condo?",
    "I need an apartment with at least five units available. Does S6102-R-9105 qualify?",
    "What is the monthly rent for S6102-R-9104, and how many units are available?",
    "Is parking included at S6102-R-9107?",
    "Can you confirm whether S6102-R-9998 exists in the listing records?",
    "Compare availability for S6102-R-9109 and S6102-R-9998.",
    "List the advertised titles and unit counts for S6102-R-9101 and S6102-R-9106.",
    "Does S6102-R-9108 have more than five available units?",
    "What type of home is S6102-R-9110, and does it have a pet policy on record?",
    "Put S6102-R-9102, S6102-R-9104, and S6102-R-9106 in order from most to fewest available units.",
    "Is S6102-R-9103 advertised as Maple Terrace, and are exactly six units available?",
    "Which of S6102-R-9101 and S6102-R-9105 are apartments with at least three available units?",
)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def seed_fixtures(client):
    fixture_path = ROOT / "reports/hw09/rental_fixtures.json"
    expected = json.loads(fixture_path.read_text())["fixtures"]
    response = client.get("/api/rentals")
    response.raise_for_status()
    existing = {row["listingCode"]: row for row in response.json()}
    for fixture in expected:
        code = fixture["listing_code"]
        facts = {
            "listingCode": code,
            "listingTitle": fixture["listing_title"],
            "propertyType": fixture["property_type"],
            "availableUnits": fixture["available_units"],
        }
        if code in existing:
            if any(existing[code].get(key) != value for key, value in facts.items()):
                raise ValueError(f"Existing fixture {code} differs from the HW9 facts")
        else:
            response = client.post(
                "/api/rentals",
                json={
                    **facts,
                    "propertyAddress": f"{code.rsplit('-', 1)[1]} Synthetic Way, San Jose",
                    "submitterEmail": "hw10-fixture@example.com",
                    "description": "Synthetic listing for Homework 10 tracing and evaluation.",
                    "termsAccepted": True,
                },
            )
            response.raise_for_status()


def login(client):
    result = client.post(
        "/auth/login",
        json={
            "username": os.environ["HW7_MODERATOR_USERNAME"],
            "password": os.environ["HW7_MODERATOR_PASSWORD"],
        },
    )
    result.raise_for_status()
    client.headers["Authorization"] = "Bearer " + result.json()["access_token"]


def ask(client, question):
    response = client.post("/api/kafka/questions", json={"question": question})
    response.raise_for_status()
    body = response.json()
    if response.headers["X-Trace-ID"] != body["request_id"]:
        raise ValueError("API response header and body disagree about request ID")
    return body


def verified_draft(log_dir, body, case_id, question):
    trace_id = body["request_id"]
    spans, linked = extract(log_dir, {trace_id: case_id})
    successful = {span["stage"] for span in spans if span["status"] == "ok"}
    generated = {
        span["stage"]
        for span in spans
        if span.get("processing_outcome") == "generated" and span["model"] != "fixture"
    }
    if (
        body["is_cached"] is not False
        or len(linked) != 1
        or linked[0]["question"] != question
        or linked[0]["final_answer"] != body["answer"]
        or not {"api_request", "cache_lookup", *HANDOFFS, *AGENTS} <= successful
        or not set(AGENTS) <= generated
        or not any(
            span["stage"] == "cache_lookup"
            and span["status"] == "ok"
            and span["cache_outcome"] == "miss"
            for span in spans
        )
    ):
        raise ValueError(f"{case_id}: {trace_id} is not a completed real cache miss")
    return linked[0]


def clear_experiment_cache(cache):
    # The caller owns this experiment namespace. Preserve the index, embedding
    # path, version checks, threshold, and every key outside its entry prefix.
    for key in cache.redis.scan_iter(match=cache.entry_prefix + "*"):
        cache.redis.delete(key)


def smoke(client, cache, log_dir, output_dir):
    clear_experiment_cache(cache)
    miss = ask(client, SMOKE)
    verified_draft(log_dir, miss, "hw10-a1-smoke", SMOKE)
    hit = ask(client, SMOKE)
    hit_id = hit["request_id"]
    spans, linked = extract(log_dir, {hit_id: "hw10-a1-hit"})
    if (
        hit["is_cached"] is not True
        or hit_id == miss["request_id"]
        or hit["answer"] != miss["answer"]
        or linked
        or [span["stage"] for span in spans] != ["api_request", "cache_lookup"]
        or any(span["status"] != "ok" or span["cache_outcome"] != "hit" for span in spans)
        or spans[1].get("source_request_id") != miss["request_id"]
    ):
        raise ValueError(f"{hit_id}: exact repeat did not bypass Kafka")
    write_json(output_dir / "smoke.json", {"question": SMOKE, "miss": miss, "hit": hit})
    print(f"Verified miss {miss['request_id']} and hit {hit_id}", flush=True)


def collect(client, cache, log_dir, output_dir):
    receipts = log_dir / "collection.jsonl"
    previous = (
        [json.loads(row) for row in receipts.read_text().splitlines()] if receipts.exists() else []
    )
    cases = []
    with receipts.open("a", encoding="utf-8") as checkpoint:
        for index, question in enumerate(QUESTIONS, 1):
            case_id = f"hw10-{index:02d}"
            if index <= len(previous):
                receipt = previous[index - 1]
                if receipt["case_id"] != case_id or receipt["question"] != question:
                    raise ValueError("The saved collection uses a different question set")
                linked = verified_draft(log_dir, receipt["response"], case_id, question)
            else:
                clear_experiment_cache(cache)
                login(client)
                body = ask(client, question)
                linked = verified_draft(log_dir, body, case_id, question)
                checkpoint.write(
                    json.dumps({"case_id": case_id, "question": question, "response": body}) + "\n"
                )
                checkpoint.flush()
            cases.append(
                {
                    key: linked[key]
                    for key in (
                        "case_id",
                        "trace_id",
                        "correlation_id",
                        "question",
                        "reference_facts",
                        "draft",
                    )
                }
            )
            print(f"{case_id} {linked['trace_id']}", flush=True)
    if len({case["trace_id"] for case in cases}) != len(QUESTIONS):
        raise ValueError("The collection contains reused trace IDs")
    write_json(output_dir / "eval_cases.json", cases)
    with (output_dir / "human_labels.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("case_id", "helpfulness"))
        writer.writerows((case["case_id"], "") for case in cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "collect"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8702")
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--owned-cache-namespace", required=True)
    parser.add_argument("--seed-fixtures", action="store_true")
    args = parser.parse_args()
    settings = CacheSettings.from_env()
    if (
        settings.namespace != args.owned_cache_namespace
        or not settings.namespace.startswith("hw10-")
        or settings.allow_stale
    ):
        parser.error("Use an owned hw10-* namespace with version enforcement enabled")
    if args.mode == "collect" and (args.output_dir / "human_labels.csv").exists():
        parser.error("The label CSV already exists; choose a fresh output directory")
    if not args.log_dir.is_dir():
        parser.error("--log-dir must point to the owned running stack's log directory")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache = SemanticCache(settings)
    try:
        with httpx.Client(base_url=args.base_url, timeout=195) as client:
            login(client)
            if args.seed_fixtures:
                seed_fixtures(client)
            run = smoke if args.mode == "smoke" else collect
            run(client, cache, args.log_dir, args.output_dir)
    finally:
        cache.close()


if __name__ == "__main__":
    main()
