"""Run and record the HW9 Part 2 workload against the real authenticated API."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter

import httpx

ENDPOINT = "/api/kafka/questions"
FIXTURES = (
    (9201, "Cedar Workshop Apartment", "apartment", 3),
    (9202, "Juniper Orchard House", "house", 1),
    (9203, "Bayview Garden Condo", "condo", 8),
    (9204, "Riverbend Townhouse", "townhouse", 0),
)
QUESTIONS = (
    ("new", "How many units are available at S6102-R-9201?"),
    ("exact", "How many units are available at S6102-R-9201?"),
    ("paraphrase", "How many units are currently available for listing S6102-R-9201?"),
    ("new", "What property type is S6102-R-9202 classified as?"),
    ("exact", "What property type is S6102-R-9202 classified as?"),
    ("paraphrase", "Which property type is listed for S6102-R-9202?"),
    ("new", "Tell me the advertised title for S6102-R-9203."),
    ("exact", "Tell me the advertised title for S6102-R-9203."),
    ("paraphrase", "What is the advertised listing title for S6102-R-9203?"),
    ("new", "What are the usual responsibilities of a rental property manager?"),
    ("new", "Is a rental security deposit typically refundable?"),
    ("new", "Is S6102-R-9204 a townhouse, and does it have any vacancies?"),
)


def login(client):
    response = client.post(
        "/auth/login",
        json={
            "username": os.environ["HW7_MODERATOR_USERNAME"],
            "password": os.environ["HW7_MODERATOR_PASSWORD"],
        },
    )
    response.raise_for_status()
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]


def create_fixtures(client):
    for code, title, kind, units in FIXTURES:
        response = client.post(
            "/api/rentals",
            json={
                "listingTitle": title,
                "listingCode": f"S6102-R-{code}",
                "propertyType": kind,
                "availableUnits": units,
                "propertyAddress": f"{code} Demonstration Avenue, San Jose, CA",
                "submitterEmail": "hw9-cache-fixture@example.com",
                "termsAccepted": True,
                "description": "Synthetic rental fact fixture for the HW9 cache demonstration.",
            },
        )
        response.raise_for_status()
        yield response.json()


def run(client, output, fixtures):
    with output.open("x", encoding="utf-8") as log:

        def record(row):
            log.write(json.dumps(row, sort_keys=True) + "\n")
            log.flush()

        record(
            {
                "event": "start",
                "student": "Pragya Apurva",
                "fixtures": fixtures,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        rows = []
        for index, (category, question) in enumerate(QUESTIONS, 1):
            started = perf_counter()
            row = {"case": index, "category": category, "question": question}
            try:
                response = client.post(ENDPOINT, json={"question": question})
                row.update(status_code=response.status_code, response=response.json())
            except (httpx.HTTPError, ValueError) as exc:
                row.update(error=type(exc).__name__)
            row["http_latency_ms"] = round((perf_counter() - started) * 1000, 3)
            row["timestamp"] = datetime.now(timezone.utc).isoformat()
            record(row)
            rows.append(row)
            body = row.get("response", {})
            decision = (
                ("HIT" if body["is_cached"] else "MISS")
                if row.get("status_code") == 200
                else "ERROR"
            )
            print(
                f"{index:02d} {category:<10} {decision:<5} {body.get('latency_ms', '-')} ms",
                flush=True,
            )

        responses = [r["response"] for r in rows if r.get("status_code") == 200]
        hits = [r["latency_ms"] for r in responses if r["is_cached"]]
        misses = [r["latency_ms"] for r in responses if not r["is_cached"]]
        summary = {
            "event": "summary",
            "total": len(rows),
            "errors": len(rows) - len(responses),
            "hits": len(hits),
            "misses": len(misses),
            "hit_rate": len(hits) / len(rows),
            "mean_hit_ms": round(mean(hits), 3) if hits else None,
            "mean_miss_ms": round(mean(misses), 3) if misses else None,
        }
        record(summary)
        print(json.dumps(summary, indent=2), flush=True)
        return 1 if summary["errors"] or not hits or not misses else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18702")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--create-fixtures", action="store_true")
    args = parser.parse_args()
    print("Pragya Apurva | DATA 260 HW9 Part 2", flush=True)
    with httpx.Client(base_url=args.base_url, timeout=195) as client:
        login(client)
        fixtures = list(create_fixtures(client)) if args.create_fixtures else []
        return run(client, args.output, fixtures)


if __name__ == "__main__":
    raise SystemExit(main())
