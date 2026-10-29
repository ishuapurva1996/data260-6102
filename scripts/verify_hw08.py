#!/usr/bin/env python3
"""Objective live Kafka smoke and recorded-failure checks; never edits application code."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "code"), str(ROOT / "scripts/hw08")]
from aiokafka.admin import AIOKafkaAdminClient
from failure_experiments import Harness, read_events
from homework_demo import RENTAL, demonstrate
from http_acceptance import accept_http
from send_question import send_question

from src.kafka_service.config import (
    DRAFTS,
    ENTITY_RESPONSES,
    INBOX,
    TASKS,
    TOPICS,
    KafkaSettings,
)
from src.kafka_service.kafka_rpc import KafkaRPC


def check_record(name, kind, passed, detail):
    return {"name": name, "kind": kind, "passed": bool(passed), "detail": detail}


def evidence_checks(root):
    checks = []
    p = root / "raw/part3"
    for label in ("before", "after"):
        rows = read_events(p / f"consumer_death_{label}.jsonl")
        observed = next(r for r in rows if r.get("event") == "observed_result")
        received = [r for r in rows if r.get("event") == "message_received"]
        committed = [r for r in rows if r.get("event") == "offset_committed"]
        expected = 0 if label == "before" else 1
        passed = (
            len(observed["outputs"]) == expected
            and observed["killed_pid"] != observed["restart_pid"]
        )
        if label == "after":
            passed &= len(received) == 2 and received[0]["offset"] == received[1]["offset"]
        passed &= bool(committed) and all(
            r["committed_offset"] == r["offset"] + 1 for r in committed
        )
        checks.append(
            check_record(
                "writer_death_" + label,
                "artifact",
                passed,
                {"receipts": len(received), "outputs": len(observed["outputs"])},
            )
        )
        rows = read_events(p / f"poison_{label}.jsonl")
        observed = next(r for r in rows if r.get("event") == "observed_result")
        dead = observed["dead_letters"]
        failed = [r for r in rows if r.get("event") == "processing_failed"]
        passed = len(observed["later_outputs"]) == expected
        if label == "after":
            passed &= len(failed) == 3 and len(dead) == 1 and dead[0]["value"]["attempts"] == 3
            good_source = observed["later_outputs"][0]["value"]["input_source"]
            passed &= good_source["partition"] == dead[0]["value"]["source"]["partition"]
            passed &= good_source["offset"] > dead[0]["value"]["source"]["offset"]
        else:
            passed &= observed["exit_code"] != 0 and len(failed) == 1 and not dead
        checks.append(
            check_record(
                "poison_" + label,
                "artifact",
                passed,
                {"failed_attempts": len(failed), "dead_letters": len(dead)},
            )
        )
        rows = read_events(p / f"pipeline_duplicate_{label}.jsonl")
        observed = next(r for r in rows if r.get("event") == "observed_result")
        count = len(observed["final_outputs"])
        checks.append(
            check_record(
                "pipeline_duplicate_" + label,
                "artifact",
                count == (2 if label == "before" else 1),
                {"final_outputs": count},
            )
        )
    for mode in ("unkeyed", "keyed"):
        with (p / f"ordering_{mode}.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        sequences = [int(r["sequence"]) for r in rows]
        partitions = sorted({int(r["task_partition"]) for r in rows})
        passed = len(rows) == 20 and set(sequences) == set(range(1, 21))
        passed &= len({r["correlation_id"] for r in rows}) == 20
        # Drafts is one partition: its actual offsets define observation order.
        passed &= [int(r["draft_offset"]) for r in rows] == sorted(
            int(r["draft_offset"]) for r in rows
        )
        if mode == "keyed":
            passed &= len(partitions) == 1 and sequences == list(range(1, 21))
        else:
            passed &= partitions == [0, 1] and len({r["instance"] for r in rows}) == 2
        checks.append(
            check_record(
                "ordering_" + mode,
                "artifact",
                passed,
                {
                    "count": len(rows),
                    "partitions": partitions,
                    "observed_sequence": sequences,
                },
            )
        )
    for label in ("before", "after"):
        rows = read_events(p / f"duplicate_{label}.jsonl")
        observed = next(r for r in rows if r.get("event") == "observed_result")
        ids = [r["value"]["rental_id"] for r in observed["responses"]]
        count = 2 if label == "before" else 1
        passed = len(ids) == 2 and len(set(ids)) == count and observed["rental_count"] == count
        checks.append(
            check_record(
                "entity_duplicate_" + label,
                "artifact",
                passed,
                {"rental_count": observed["rental_count"], "uuids": ids},
            )
        )
    rows = read_events(p / "publish_commit_boundary.jsonl")
    observed = next(r for r in rows if r.get("event") == "observed_result")
    passed = len(observed["final_outputs"]) == 1
    passed &= any(r.get("event") == "duplicate_cached" and r.get("stage") == "writer" for r in rows)
    passed &= any(
        r.get("event") == "duplicate_suppressed" and r.get("stage") == "reviewer" for r in rows
    )
    checks.append(
        check_record(
            "publish_commit_boundary",
            "artifact",
            passed,
            {"final_outputs": len(observed["final_outputs"])},
        )
    )
    manifest = json.loads((p / "ordering_manifest.json").read_text())
    checks.append(
        check_record(
            "ordering_seed",
            "artifact",
            manifest["verify_seed"] == 266102,
            manifest["verify_seed"],
        )
    )
    return checks


async def pipeline_smoke(runtime, output, model):
    h = Harness(runtime, output)
    await h.start()
    try:
        logs = []
        for stage, topic in (
            ("planner", INBOX),
            ("writer", TASKS),
            ("reviewer", DRAFTS),
        ):
            group = f"verify-{uuid4().hex}-{stage}"
            await h.prime(topic, group)
            proc, log = h.spawn(stage + "-live", group, "live-" + stage, model=model)
            await h.wait_event(log, "consumer_ready")
            logs.append(log)
        result = await send_question(
            "How does Kafka message ordering affect updates to the same rental listing?",
            run_id=h.run_id,
            rental_id="hw8-synthetic-6102",
            timeout=180,
        )
        cid = result["request"]["correlation_id"]
        events = [r for log in logs for r in read_events(log)]
        journey = [r for r in events if r.get("correlation_id") == cid]
        output.mkdir(parents=True, exist_ok=True)
        (output / "journey.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in sorted(journey, key=lambda r: r["timestamp"]))
        )
        (output / "final.json").write_text(json.dumps(result, indent=2) + "\n")
        ready = [r for r in events if r.get("event") == "consumer_ready"]
        (output / "processes.json").write_text(json.dumps(ready, indent=2) + "\n")
        passed = result["final"]["correlation_id"] == cid and bool(
            result["final"]["answer"].strip()
        )
        passed &= len({r["pid"] for r in ready}) == 3
        passed &= {r["stage"] for r in ready} == {"planner", "writer", "reviewer"}
        passed &= len([r for r in journey if r.get("event") == "output_published"]) == 3
        return check_record(
            "three_process_pipeline",
            "live Kafka + " + model,
            passed,
            {"correlation_id": cid, "process_ids": [r["pid"] for r in ready]},
        )
    finally:
        await h.close()


async def http_smoke(base_url, evidence_dir):
    result = await accept_http(base_url, evidence_dir)
    return [
        check_record(c["name"], "live HTTP + Kafka", c["passed"], c["detail"])
        for c in result["checks"]
    ]


async def verify(args):
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    os.environ["HW8_SOURCE_COMMIT"] = commit
    checks = []
    if args.require_ref:
        target = subprocess.check_output(
            ["git", "rev-parse", args.require_ref + "^{commit}"], cwd=ROOT, text=True
        ).strip()
        checks.append(
            check_record(
                "tested_ref",
                "git",
                target == commit,
                {"ref": args.require_ref, "target": target},
            )
        )
    admin = AIOKafkaAdminClient(bootstrap_servers=KafkaSettings.from_env().bootstrap_servers)
    await admin.start()
    try:
        topics = await admin.describe_topics(list(TOPICS))
        actual = {t["topic"]: len(t["partitions"]) for t in topics}
        checks.append(
            check_record("seven_topic_partitions", "live Kafka", actual == TOPICS, actual)
        )
    finally:
        await admin.close()
    rpc = KafkaRPC()
    await rpc.start()
    try:
        roundtrip = await demonstrate(rpc.make_request)
        output = args.evidence_dir / "raw/part1"
        output.mkdir(parents=True, exist_ok=True)
        (output / "roundtrip.json").write_text(json.dumps(roundtrip, indent=2) + "\n")
        checks.append(
            check_record(
                "rental_create_get",
                "live Kafka",
                roundtrip["passed"],
                {"correlation_id": roundtrip["correlation_id"]},
            )
        )
        request = roundtrip["exchanges"][0]["request"]
        replay = await rpc.make_request(request)
        checks.append(
            check_record(
                "rental_replay_same_uuid",
                "live Kafka",
                replay["rental_id"] == roundtrip["exchanges"][0]["response"]["rental_id"],
                replay,
            )
        )
        validation = []
        for operation, data in [
            ("CREATE_RENTAL", {}),
            ("CREATE_RENTAL", {**RENTAL, "termsAccepted": False}),
            ("UNKNOWN", {}),
            ("GET_RENTAL", {"rental_id": str(uuid4())}),
        ]:
            cid = str(uuid4())
            request = {
                "correlation_id": cid,
                "reply_to": ENTITY_RESPONSES,
                "operation": operation,
                "data": data,
            }
            response = await rpc.make_request(request)
            passed = (
                response.get("success") is False
                and response.get("correlation_id") == cid
                and bool(response.get("error"))
            )
            validation.append({"request": request, "response": response, "passed": passed})
        (output / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
        checks.append(
            check_record(
                "clean_domain_errors",
                "live Kafka",
                all(r["passed"] for r in validation),
                validation,
            )
        )
    finally:
        await rpc.stop()
    if not args.skip_http:
        try:
            checks.extend(await http_smoke(args.base_url, args.evidence_dir))
        except (httpx.HTTPError, ValueError) as exc:
            checks.append(
                check_record(
                    "authenticated_fastapi_wrapper",
                    "live HTTP",
                    False,
                    type(exc).__name__,
                )
            )
    if not args.skip_pipeline:
        checks.append(
            await pipeline_smoke(args.runtime_dir, args.evidence_dir / "raw/part2", args.model)
        )
    if not args.skip_artifacts:
        try:
            checks.extend(evidence_checks(args.evidence_dir))
        except (OSError, ValueError, KeyError, StopIteration) as exc:
            checks.append(check_record("failure_artifacts", "artifact", False, str(exc)))
    result = {
        "homework": 8,
        "sid4": 6102,
        "commit_hash": commit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seed": 6102,
        "verify_seed": 266102,
        "configuration": {
            "port_base": 8702,
            "prefix": "s6102",
            "domain_id": 6,
            "model": args.model,
            "temperature": 0,
            "context_window": 4096,
            "output_limit": 256,
            "retry_attempts": 3,
        },
        "checks": checks,
        "passed": all(r["passed"] for r in checks),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return result["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "reports/hw08")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/hw08/verification.json")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--require-ref")
    parser.add_argument("--skip-pipeline", action="store_true")
    parser.add_argument("--skip-http", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8702")
    parser.add_argument("--skip-artifacts", action="store_true")
    raise SystemExit(0 if asyncio.run(verify(parser.parse_args())) else 1)
