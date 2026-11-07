"""Verify frozen HW9 evidence and optionally exercise the integrated live system."""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]
EVIDENCE = ROOT / "reports/hw09"
FROZEN_COMMIT = "3511ae67588f61eeff4199aa8f4db294aca04c57"
FROZEN_SHA = "4c180dd5a8b5dbd007797225889d1cb7e0921339d0670683b225674ee76f0c26"
SOURCES = {
    "counter": "bd82926172d80afbb4e80f10b02f9adc1d7930f0",
    "cache": "6938c71110845b7b73c53b795b709399f8a523a1",
    "experiments": "f7e5af838ede505db39860be7b6d0b0977b0752c",
    "agents": "c00f72e9dc1e11c1aa361179732dd98ca4dda466",
}


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def events(path):
    rows = []
    for line in path.read_text().splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def verify_sources():
    for source in ["hw8", FROZEN_COMMIT, *SOURCES.values()]:
        subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", source, "HEAD"], check=True
        )
    assert digest(EVIDENCE / "cache_cases.yaml") == FROZEN_SHA
    frozen = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", FROZEN_COMMIT + ":reports/hw09/cache_cases.yaml"]
    )
    assert hashlib.sha256(frozen).hexdigest() == FROZEN_SHA
    paths = [
        "src/hw09/semantic_cache.py",
        "code/web_application/routers/kafka_questions.py",
        "code/web_application/rental_facts.py",
        "src/kafka_agents",
        "src/model_client.py",
    ]
    assert not git("diff", SOURCES["experiments"], "HEAD", "--", *paths)
    paths = ["src/hw09_agents.py", "scripts/hw09/part4_agents.py", "src/model_client.py"]
    assert not git("diff", SOURCES["agents"], "HEAD", "--", *paths)
    return {
        "ancestry": "PASS",
        "frozen_yaml_sha256": FROZEN_SHA,
        "measured_cache_and_agent_code_unchanged": True,
        "sources": SOURCES,
    }


def verify_part4():
    from scripts.hw09.part4_agents import check_disjoint, load_cases
    from src.hw09_agents import MAX_ATTEMPTS, Answer, EvaluatorAgent

    base = EVIDENCE / "raw/part4"
    freeze, held = read(base / "freeze.json"), read(base / "held_out_results.json")
    assert digest(base / "freeze.json") == (base / "freeze.sha256").read_text().strip()
    assert held["freeze_sha256"] == digest(base / "freeze.json")
    assert MAX_ATTEMPTS == freeze["maximum_attempts"] == 2
    for path, sha in freeze["files_sha256"]["code"].items():
        assert digest(ROOT / path) == sha
    assert digest(base / "lessons.json") == freeze["files_sha256"]["lessons_json"]
    for name, sha in freeze["files_sha256"]["datasets"].items():
        assert digest(base / "data" / name) == sha
        assert held["dataset_sha256"][name] == sha
    reference = read(base / "data/rental_reference.json")
    splits = []
    for name, sha in held["dataset_sha256"].items():
        assert digest(base / "data" / name) == sha
        if name != "rental_reference.json":
            splits.append(load_cases((base / "data" / name).read_bytes(), reference))
    check_disjoint(*splits)
    test = read(base / "data/test_data.json")
    assert git("hash-object", str(base / "data/test_data.json")) == freeze["held_out_git_blob"]
    summaries = []
    for variant, settings in zip(held["variants"], freeze["variants"], strict=True):
        assert [variant["variant"], variant["repair"], variant["lesson_snapshot"]] == settings
        assert variant["test_sha256"] == held["dataset_sha256"]["test_data.json"]
        assert [case["question"] for case in variant["cases"]] == test
        correct = 0
        for case in variant["cases"]:
            attempts = case["attempts"]
            assert 1 <= len(attempts) <= (2 if variant["repair"] else 1)
            question = case["question"]
            score = EvaluatorAgent().evaluate(
                question, reference[question["listing_id"]], Answer(**attempts[-1]["answer"])
            )
            assert (
                asdict(score)
                | {
                    "incorrect_fields": list(score.incorrect_fields),
                    "unsupported_claims": list(score.unsupported_claims),
                }
                == case["offline_grade"]
            )
            correct += score.result == "PASS"
        expected = {
            "correct": correct,
            "incorrect": len(test) - correct,
            "average_attempts": mean(len(c["attempts"]) for c in variant["cases"]),
            "average_latency_ms": mean(c["latency_ms"] for c in variant["cases"]),
        }
        assert variant["metrics"] == expected
        summaries.append({"variant": variant["variant"], **expected})
    dev = read(base / "development.json")
    assert [a["grade"]["result"] for a in dev["controlled_revision"]["attempts"]] == [
        "REVISE",
        "PASS",
    ]
    assert [a["grade"]["result"] for a in dev["controlled_stop"]["attempts"]] == [
        "REVISE",
        "REVISE",
    ]
    assert dev["lesson_reuse"]["lesson_ids"] == ["rental-ready-units-v1"]
    assert dev["lesson_reuse"]["final_evaluation"]["result"] == "PASS"
    validation = read(base / "validation.json")
    assert validation["accepted"] and not validation["regressions"]
    return {
        "held_out_sha256": held["dataset_sha256"]["test_data.json"],
        "independently_regraded": 40,
        "identical_inputs": True,
        "max_attempts": 2,
        "revision_stop_reuse_validation": "PASS",
        "results": summaries,
    }


def verify_saved(runtime):
    from scripts.hw09.analyze_cache_experiments import verify

    with tempfile.TemporaryDirectory(dir=runtime) as scratch:
        copy = Path(scratch) / "part3"
        shutil.copytree(EVIDENCE / "raw/part3", copy)
        _, rows, summaries, _, _ = verify(copy)
        assert summaries == read(EVIDENCE / "raw/part3/audited-threshold-summary.json")
        assert events(copy / "audited-requests.jsonl") == events(
            EVIDENCE / "raw/part3/audited-requests.jsonl"
        )
    assert len(rows) == 200
    assert sum(r["automatic_correct"] != r["correct"] for r in rows) == 2
    row = next(r for r in summaries if r["threshold"] == 0.85)
    assert row["incorrect_cached_answers"] == 13
    counter = read(EVIDENCE / "raw/part1/counter-run.json")
    assert counter["counts"] == list(range(1, 26))
    assert counter["mysql_checkpoints"] == {"9": 0, "10": 10, "20": 20, "25": 20}
    return {
        "part1_saved_counter": "PASS",
        "part3_requests": 200,
        "scoring_corrections": 2,
        "part3_audited_results": summaries,
        "part4": verify_part4(),
    }


async def broker_offsets():
    from aiokafka import AIOKafkaConsumer, TopicPartition

    from src.kafka_service.config import FINAL, INBOX, KafkaSettings

    consumer = AIOKafkaConsumer(
        bootstrap_servers=KafkaSettings.from_env().bootstrap_servers,
        group_id=None,
        enable_auto_commit=False,
    )
    await consumer.start()
    try:
        partitions = [TopicPartition(topic, 0) for topic in (INBOX, FINAL)]
        result = await consumer.end_offsets(partitions)
        return {p.topic: offset for p, offset in result.items()}
    finally:
        await consumer.stop()


def verify_live(args, runtime):
    api_ready = [e for e in events(args.api_log) if e.get("event") == "semantic_cache_ready"][-1]
    source_commit = git("rev-parse", "HEAD")
    assert api_ready["source_commit"] == source_commit

    import httpx
    from redis import Redis
    from sqlalchemy import text
    from web_application.database import db_session_basede26 as engine

    from scripts.hw09.cache_experiments import unambiguous_units
    from scripts.hw09.verify_counter import login
    from scripts.hw09.verify_counter import verify as verify_counter

    redis = Redis.from_url(os.environ["HW9_REDIS_URL"])

    def version():
        with engine.connect() as db:
            return db.execute(
                text("SELECT version FROM rental_data_version WHERE id=1")
            ).scalar_one()

    with httpx.Client(base_url=args.base_url, timeout=190) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/").status_code == 200
        assert client.post("/api/kafka/questions", json={"question": "test"}).status_code == 401
        counter = verify_counter(args.base_url, redis)
        auth = login(client, "MODERATOR")
        with engine.connect() as db:
            primary_id = db.execute(
                text("SELECT id FROM rentals WHERE listing_code=:code"),
                {"code": counter["primary_listing"]},
            ).scalar_one()
        primary = {"id": primary_id, "listingCode": counter["primary_listing"]}
        before = version()
        for _ in range(10):
            assert client.get(f"/api/rentals/{primary['id']}", headers=auth).status_code == 200
        assert version() == before
        with engine.connect() as db:
            assert (
                db.execute(
                    text("SELECT view_count FROM rentals WHERE id=:id"), {"id": primary["id"]}
                ).scalar_one()
                == 30
            )
        created = client.post(
            "/api/rentals",
            headers=auth,
            json={
                "listingTitle": "HW9 Integrated Version Fixture",
                "propertyAddress": "6102 Test Avenue, San Jose",
                "submitterEmail": "integration@example.com",
                "description": "Synthetic integration verification fixture.",
                "propertyType": "apartment",
                "termsAccepted": True,
                "availableUnits": 3,
            },
        )
        assert created.status_code == 201
        listing = created.json()
        assert version() == before + 1
        question = f"How many units are available at {listing['listingCode']}?"
        requests = []

        def ask(label):
            response = client.post(
                "/api/kafka/questions", headers=auth, json={"question": question}
            )
            assert response.status_code == 200, response.status_code
            result = response.json()
            requests.append({"label": label, "question": question, "response": result})
            print(
                f"{label}: cached={result['is_cached']} similarity={result['similarity']} answer={result['answer']}",
                flush=True,
            )
            return result

        miss = ask("fresh_miss_3")
        assert not miss["is_cached"] and unambiguous_units(miss["answer"], 3)
        offsets_before = asyncio.run(broker_offsets())
        hit = ask("exact_hit_3")
        assert hit["is_cached"] and hit["answer"] == miss["answer"]
        offsets_after = asyncio.run(broker_offsets())
        assert offsets_before == offsets_after
        v = version()
        for _ in range(10):
            assert client.get(f"/api/rentals/{listing['id']}", headers=auth).status_code == 200
        assert version() == v
        assert ask("hit_after_view_checkpoint_3")["is_cached"]
        changed = client.put(
            f"/api/rentals/{listing['id']}",
            headers=auth,
            json={
                "listingTitle": listing["listingTitle"],
                "propertyAddress": listing["propertyAddress"],
                "availableUnits": 1,
            },
        )
        assert changed.status_code == 200 and version() == v + 1
        fresh = ask("invalidated_miss_1")
        assert not fresh["is_cached"] and unambiguous_units(fresh["answer"], 1)
        assert ask("fresh_hit_1")["is_cached"]
        failed_version = version()
        failed = client.put(
            f"/api/rentals/{listing['id']}",
            headers=auth,
            json={
                "listingTitle": listing["listingTitle"],
                "propertyAddress": listing["propertyAddress"],
                "listingCode": primary["listingCode"],
                "availableUnits": 9,
            },
        )
        assert failed.status_code == 409 and version() == failed_version
        assert (
            client.get(f"/api/rentals/{listing['id']}", headers=auth).json()["availableUnits"] == 1
        )
        assert client.delete(f"/api/rentals/{listing['id']}", headers=auth).status_code == 204
        assert version() == failed_version + 1

    api_events = events(args.api_log)
    ready = [e for e in api_events if e.get("event") == "semantic_cache_ready"][-1]
    assert ready["threshold"] == 0.85 and ready["allow_stale"] is False
    assert ready["source_commit"] == source_commit
    correlated = {
        e["request_id"]: e for e in api_events if e.get("event") == "semantic_cache_result"
    }
    stage_events = [
        e
        for stage in ("planner", "writer", "reviewer")
        for e in events(args.stage_log_dir / f"{stage}.log")
    ]
    for request in requests:
        result = request["response"]
        identity = result["request_id"]
        event = correlated[identity]
        assert event["source_commit"] == source_commit
        generations = [
            e
            for e in stage_events
            if e.get("event") == "model_result" and e.get("correlation_id") == identity
        ]
        assert event["version_enforced"] and event["error"] is None
        assert event["pipeline_attempted"] is not result["is_cached"]
        assert len(generations) == (0 if result["is_cached"] else 3)
        assert all(e["fixture"] is False for e in generations)
        assert all(e["source_commit"] == source_commit for e in generations)
        pipeline_events = [
            e
            for e in api_events
            if e.get("event") in ("question_sent", "final_received")
            and e.get("correlation_id") == identity
        ]
        assert all(e["source_commit"] == source_commit for e in pipeline_events)
        assert len(pipeline_events) == (0 if result["is_cached"] else 2)
        assert sum(
            e.get("event") == "question_sent" and e.get("correlation_id") == identity
            for e in api_events
        ) == (0 if result["is_cached"] else 1)
        request["cache_event"] = event
        request["generative_model_calls"] = len(generations)
    assert len({r["response"]["request_id"] for r in requests}) == len(requests)
    namespace = ready["namespace"]
    keys = [key.decode() for key in redis.scan_iter(match=f"s6102:hw9:semantic:{namespace}:*")]
    assert keys and all(k.startswith("s6102:") for k in keys)
    redis.close()
    engine.dispose()
    development = runtime / "part4-development"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/hw09/part4_agents.py"),
            "develop",
            "--output",
            str(development),
        ],
        check=True,
    )
    demo = read(development / "development.json")
    assert demo["model"] == read(EVIDENCE / "raw/part4/freeze.json")["model"]
    assert (
        demo["controlled_revision"]["attempt_count"]
        == demo["controlled_stop"]["attempt_count"]
        == 2
    )
    assert demo["controlled_stop"]["final_evaluation"]["result"] == "REVISE"
    return {
        "counter": counter,
        "view_checkpoints_preserve_fact_version": True,
        "create_update_delete_advance_version": True,
        "failed_write_rolls_back_version": True,
        "hit_broker_offsets_before": offsets_before,
        "hit_broker_offsets_after": offsets_after,
        "cache_keys": keys,
        "requests": requests,
        "part4_live_controlled_development": "PASS",
        "configuration": {"port": 8702, "threshold": 0.85, "version_enforced": True},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=EVIDENCE / "verification.json")
    parser.add_argument("--require-ref")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8702")
    parser.add_argument("--api-log", type=Path)
    parser.add_argument("--stage-log-dir", type=Path)
    args = parser.parse_args()
    if not __debug__:
        parser.error("Assertions must be enabled.")
    if args.live and (args.api_log is None or args.stage_log_dir is None):
        parser.error("Live checks require --api-log and --stage-log-dir.")
    if args.runtime_dir.resolve().is_relative_to(ROOT):
        parser.error("Runtime files must stay outside the repository.")
    args.runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime = Path(tempfile.mkdtemp(prefix="verify-", dir=args.runtime_dir))
    receipt = {
        "student": "Pragya Apurva",
        "homework": 9,
        "SID4": "6102",
        "PREFIX": "s6102",
        "SEED": 6102,
        "VERIFY_SEED": 266102,
        "DOMAIN_ID": 6,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": git("rev-parse", "HEAD"),
        "model": "qwen2.5:7b",
        "threshold": 0.85,
        "version_enforced": True,
    }
    print(f"Pragya Apurva | DATA 260 HW9 verifier | {receipt['started_at_utc']}", flush=True)
    try:
        if args.require_ref:
            assert receipt["source_commit"] == git("rev-parse", f"{args.require_ref}^{{}}")
            assert not git("status", "--porcelain", "--untracked-files=no")
        receipt["sources"] = verify_sources()
        receipt["saved_evidence"] = verify_saved(runtime)
        if args.live:
            receipt["live"] = verify_live(args, runtime)
        receipt["status"] = "PASS"
        receipt["scope"] = (
            "saved evidence and live integration" if args.live else "saved evidence only"
        )
    except Exception as error:
        receipt["status"] = "FAIL"
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        receipt["finished_at_utc"] = datetime.now(UTC).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"HW9 verification: {receipt.get('status')} | {args.output}", flush=True)


if __name__ == "__main__":
    main()
