"""Reproduce Part 3 through the real authenticated HTTP and snapshot interfaces."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import httpx

from scripts.hw06.runtime_lease import RuntimeLease
from scripts.hw09.cache_part2 import login

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "reports/hw09"
FROZEN_COMMIT = "3511ae67588f61eeff4199aa8f4db294aca04c57"
FROZEN_SHA = "4c180dd5a8b5dbd007797225889d1cb7e0921339d0670683b225674ee76f0c26"
THRESHOLDS = (0.75, 0.80, 0.85, 0.90, 0.95)
BASE_URL = "http://127.0.0.1:18708"
WORDS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def append(path, value):
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def load_cases():
    path = DATA / "cache_cases.yaml"
    frozen_bytes = path.read_bytes()
    assert hashlib.sha256(frozen_bytes).hexdigest() == FROZEN_SHA
    assert (
        subprocess.check_output(
            ["git", "show", f"{FROZEN_COMMIT}:reports/hw09/cache_cases.yaml"], cwd=ROOT
        )
        == frozen_bytes
    )
    doc = json.loads(frozen_bytes)
    assert len(doc["cases"]) == 40
    assert Counter(c["category"] for c in doc["cases"]) == {
        "exact": 10,
        "paraphrase": 10,
        "similar_different": 10,
        "unrelated": 10,
    }
    return doc


def grade(answer, expected):
    if "all_regex" in expected:
        return all(re.search(p, answer, re.I) for p in expected["all_regex"])
    codes = set(re.findall(r"S6102-R-\d+", answer, re.I))
    if any(c.upper() != expected["listing_code"] for c in codes):
        return False
    value = expected["value"]
    if expected["field"] == "available_units":
        return bool(re.search(rf"\b(?:{value}|{WORDS[value]})\b", answer, re.I))
    return bool(re.search(rf"\b{re.escape(value)}\b", answer, re.I))


def unambiguous_units(answer, units):
    text = re.sub(r"S6102-R-\d+", "", answer, flags=re.I).lower()
    word_values = {word: number for number, word in WORDS.items()}
    tokens = re.findall(r"\b(?:\d+|" + "|".join(word_values) + r")\b", text)
    values = {int(t) if t.isdecimal() else word_values[t] for t in tokens}
    return (
        values == {units}
        and not re.search(r"\b(?:not|incorrect|unavailable|no)\b", text)
        and bool(
            re.search(
                rf"\b(?:{units}|{WORDS[units]})\s+(?:available\s+)?units?\b", text
            )
        )
    )


def summarize(rows, costs):
    hits = sum(r["is_cached"] for r in rows)
    wrong_hits = sum(r["is_cached"] and not r["correct"] for r in rows)
    negatives = [r for r in rows if not r["should_hit"]]
    return {
        "requests": len(rows),
        "hits": hits,
        "misses": len(rows) - hits,
        "incorrect_cached_answers": wrong_hits,
        "hit_rate": hits / len(rows),
        "false_hit_rate": wrong_hits / len(rows),
        "negative_acceptance_rate": sum(r["is_cached"] for r in negatives)
        / len(negatives),
        "wrong_live_answers": sum(
            not r["is_cached"] and not r["correct"] for r in rows
        ),
        "mean_http_latency_ms": mean(r["http_latency_ms"] for r in rows),
        "total_cost": (len(rows) - hits) * costs["miss_cost"]
        + wrong_hits * costs["false_hit_cost"],
    }


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_event(path, name, process):
    for _ in range(300):
        if name in path.read_text():
            return
        if process.poll() is not None:
            raise RuntimeError(f"Process failed; inspect {path}")
        time.sleep(0.2)
    raise TimeoutError(f"No {name}; inspect {path}")


@contextmanager
def stages(runtime, phase):
    processes, streams = [], []
    try:
        for stage in ("planner", "writer", "reviewer"):
            path = runtime / f"{phase}-{stage}.log"
            stream = path.open("x")
            streams.append(stream)
            p = subprocess.Popen(
                [
                    sys.executable,
                    f"scripts/hw08/{stage}.py",
                    "--state-dir",
                    str(runtime / "stages"),
                ],
                cwd=ROOT,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
            processes.append(p)
            wait_event(path, '"event": "consumer_ready"', p)
        yield
    finally:
        for p in processes:
            stop(p)
        for stream in streams:
            stream.close()


@contextmanager
def api(runtime, namespace, threshold, stale=False):
    env = dict(
        os.environ,
        HW9_CACHE_NAMESPACE=namespace,
        HW9_CACHE_THRESHOLD=str(threshold),
        HW9_CACHE_DEMO_ALLOW_STALE=str(int(stale)),
    )
    path = runtime / f"api-{namespace}-{'stale' if stale else 'enforced'}.log"
    with path.open("x") as stream:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "web_application.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18708",
            ],
            cwd=ROOT,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_event(path, '"event": "semantic_cache_ready"', process)
            with httpx.Client(
                base_url=BASE_URL, timeout=195, trust_env=False
            ) as client:
                for _ in range(100):
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        time.sleep(0.1)
                login(client)
                yield client, path
        finally:
            stop(process)


def request(client, question, log_path):
    started = time.perf_counter()
    response = None
    try:
        response = client.post("/api/kafka/questions", json={"question": question})
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        append(
            log_path,
            {
                "timestamp": stamp(),
                "question": question,
                "error": type(exc).__name__,
                "http_latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "status_code": response.status_code if response is not None else None,
                "response_text": response.text if response is not None else None,
            },
        )
        raise
    row = {
        "timestamp": stamp(),
        "question": question,
        "status_code": response.status_code,
        "http_latency_ms": elapsed,
        "response": body,
    }
    append(log_path, row)
    response.raise_for_status()
    return row


def event_for(path, request_id):
    for _ in range(30):
        for line in path.read_text().splitlines():
            if line.startswith("{"):
                event = json.loads(line)
                if (
                    event.get("event") == "semantic_cache_result"
                    and event.get("request_id") == request_id
                ):
                    return event
        time.sleep(0.05)
    raise RuntimeError("Missing correlated cache event")


def snapshot(runtime, namespace, operation):
    env = dict(os.environ, HW9_CACHE_NAMESPACE=namespace)
    command = [
        sys.executable,
        "-m",
        "scripts.hw09.cache_snapshot",
        operation,
        str(runtime / "seed.json"),
    ]
    if operation == "export":
        command += ["--questions", str(runtime / "seed-questions.json")]
    result = subprocess.check_output(command, cwd=ROOT, env=env, text=True)
    append(runtime / "snapshot-operations.jsonl", json.loads(result))
    print(result.strip(), flush=True)


def seed(runtime, doc):
    fixture_doc = json.loads((DATA / "rental_fixtures.json").read_text())
    with api(runtime, "c-fixtures-01", 1) as (client, _):
        assert client.get("/api/rentals").json() == [], (
            "Dedicated database must begin empty"
        )
        created = []
        for f in [*fixture_doc["fixtures"], fixture_doc["stale_fixture"]]:
            response = client.post(
                "/api/rentals",
                json={
                    "listingTitle": f["listing_title"],
                    "listingCode": f["listing_code"],
                    "propertyType": f["property_type"],
                    "availableUnits": f["available_units"],
                    "propertyAddress": f"{f['listing_code'].split('-')[-1]} Synthetic Way, San Jose",
                    "submitterEmail": "hw9-experiment@example.com",
                    "termsAccepted": True,
                    "description": "Synthetic rental fixture for the frozen HW9 threshold study.",
                },
            )
            response.raise_for_status()
            created.append(response.json())
        write_json(runtime / "fixture-receipts.json", created)
    from src.model_client import build_ollama_client

    model = build_ollama_client(
        "qwen2.5:7b",
        os.environ["OLLAMA_BASE_URL"],
        0,
        180,
        context_window=4096,
        output_limit=256,
        seed=6102,
    )
    model.complete([{"role": "user", "content": "Say ready."}])
    write_json(runtime / "seed-questions.json", [s["question"] for s in doc["seeds"]])
    with api(runtime, "c-seed-01", 1) as (client, log):
        verified = []
        for s in doc["seeds"]:
            row = request(client, s["question"], runtime / "seed-requests.jsonl")
            body = row["response"]
            event = event_for(log, body["request_id"])
            expected = {
                "listing_code": s["listing_code"],
                "field": s["field"],
                "value": s["expected"],
            }
            assert not body["is_cached"] and event["cache_write"] == "stored"
            assert grade(body["answer"], expected), body["answer"]
            verified.append(
                {**row, "seed_id": s["id"], "correct": True, "cache_event": event}
            )
            print(s["id"], body["answer"], flush=True)
        write_json(runtime / "seed-review.json", verified)
    snapshot(runtime, "c-seed-01", "export")
    print(
        "Seed SHA256",
        hashlib.sha256((runtime / "seed.json").read_bytes()).hexdigest(),
        flush=True,
    )


def sweep(runtime, doc):
    assert (runtime / "seed-reviewed.json").exists(), (
        "Review the ten live seeds before sweeping"
    )
    summaries = []
    for threshold in THRESHOLDS:
        namespace = f"c-sweep-{round(threshold * 100):03d}-01"
        snapshot(runtime, namespace, "restore")
        rows = []
        with api(runtime, namespace, threshold) as (client, log):
            for case in doc["cases"]:
                row = request(
                    client,
                    case["question"],
                    runtime / f"requests-{threshold:.2f}.jsonl",
                )
                body = row["response"]
                event = event_for(log, body["request_id"])
                assert not event["error"]
                assert event["version_enforced"]
                assert event["pipeline_attempted"] != body["is_cached"]
                row.update(
                    case_id=case["id"],
                    category=case["category"],
                    should_hit=case["should_hit"],
                    expected=case["expected"],
                    correct=grade(body["answer"], case["expected"]),
                    is_cached=body["is_cached"],
                    cache_event=event,
                    threshold=threshold,
                )
                rows.append(row)
                append(runtime / "scored-requests.jsonl", row)
                print(
                    threshold,
                    case["id"],
                    "HIT" if body["is_cached"] else "MISS",
                    "correct" if row["correct"] else "WRONG",
                    row["http_latency_ms"],
                    flush=True,
                )
        summary = dict(threshold=threshold, **summarize(rows, doc["cost_model"]))
        summaries.append(summary)
        write_json(runtime / "threshold-summary.json", summaries)
    chosen = min(summaries, key=lambda r: (r["total_cost"], -r["threshold"]))[
        "threshold"
    ]
    write_json(
        runtime / "chosen-threshold.json",
        {"threshold": chosen, "rule": doc["cost_model"]["tie_break"]},
    )


def stale_demo(runtime):
    fixtures = json.loads((runtime / "fixture-receipts.json").read_text())
    fixture = next(f for f in fixtures if f["listingCode"] == "S6102-R-9199")
    question = "How many units are available at S6102-R-9199?"
    namespace = "stale-demo-c-01"
    traces = []
    with api(runtime, namespace, 0.95, stale=True) as (client, log):
        before = client.get(f"/api/rentals/{fixture['id']}").json()
        assert before["availableUnits"] == 3
        row = request(client, question, runtime / "stale-requests.jsonl")
        row.update(
            step="prime_3", cache_event=event_for(log, row["response"]["request_id"])
        )
        assert not row["response"]["is_cached"]
        assert grade(
            row["response"]["answer"],
            {"listing_code": "S6102-R-9199", "field": "available_units", "value": 3},
        )
        assert unambiguous_units(row["response"]["answer"], 3)
        traces.append(row)
        response = client.put(
            f"/api/rentals/{fixture['id']}",
            json={
                "listingTitle": before["listingTitle"],
                "propertyAddress": before["propertyAddress"],
                "availableUnits": 1,
            },
        )
        response.raise_for_status()
        write_json(
            runtime / "stale-mutation.json",
            {"before": before, "after": response.json(), "timestamp": stamp()},
        )
        row = request(client, question, runtime / "stale-requests.jsonl")
        row.update(
            step="stale_hit_3_after_update_to_1",
            cache_event=event_for(log, row["response"]["request_id"]),
        )
        assert (
            row["response"]["is_cached"]
            and row["response"]["answer"] == traces[0]["response"]["answer"]
        )
        assert (
            row["cache_event"]["matched_data_version"]
            < row["cache_event"]["data_version"]
        )
        traces.append(row)
    with api(runtime, namespace, 0.95) as (client, log):
        for step, cached in (
            ("enforced_fresh_miss_1", False),
            ("enforced_fresh_hit_1", True),
        ):
            row = request(client, question, runtime / "stale-requests.jsonl")
            row.update(
                step=step, cache_event=event_for(log, row["response"]["request_id"])
            )
            assert row["response"]["is_cached"] == cached
            assert grade(
                row["response"]["answer"],
                {
                    "listing_code": "S6102-R-9199",
                    "field": "available_units",
                    "value": 1,
                },
            )
            assert unambiguous_units(row["response"]["answer"], 1)
            traces.append(row)
    write_json(runtime / "stale-trace.json", traces)
    chosen = json.loads((runtime / "chosen-threshold.json").read_text())["threshold"]
    with api(runtime, "c-chosen-smoke-01", chosen) as (client, log):
        smoke = [
            request(client, question, runtime / "chosen-smoke.jsonl") for _ in range(2)
        ]
        assert [r["response"]["is_cached"] for r in smoke] == [False, True]
    print(
        "PASS: stale 3 after update to 1; enforced miss and hit at 1; chosen threshold smoke",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("seed", "sweep", "stale"))
    parser.add_argument("--runtime", required=True, type=Path)
    args = parser.parse_args()
    doc = load_cases()
    runtime = args.runtime.resolve()
    assert not runtime.is_relative_to(ROOT), "Runtime must stay outside the repository"
    with RuntimeLease(
        runtime.parent / "ollama-shared",
        owner="HW9 Session C / Pragya Apurva",
        purpose=f"Exclusive Part 3 {args.phase} real model measurement",
    ):
        append(
            runtime / "lease-windows.jsonl",
            {"event": "acquired", "phase": args.phase, "timestamp": stamp()},
        )
        print("Pragya Apurva | DATA 260 HW9 Part 3 |", args.phase, stamp(), flush=True)
        try:
            with stages(runtime, args.phase):
                {"seed": seed, "sweep": sweep, "stale": lambda r, _: stale_demo(r)}[
                    args.phase
                ](runtime, doc)
        finally:
            append(
                runtime / "lease-windows.jsonl",
                {"event": "released", "phase": args.phase, "timestamp": stamp()},
            )


if __name__ == "__main__":
    main()
