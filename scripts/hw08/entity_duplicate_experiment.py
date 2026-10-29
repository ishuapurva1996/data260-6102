#!/usr/bin/env python3
"""Run with the Compose entity worker stopped; restores no shared services itself."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code"), str(ROOT / "scripts/hw08")]
from failure_experiments import Harness, read_events
from homework_demo import RENTAL

from src.kafka_service.config import ENTITY_REQUESTS, ENTITY_RESPONSES


async def run(args):
    h = Harness(args.runtime_dir, args.output_dir)
    await h.start()
    summary = {}
    try:
        for label in ("before", "after"):
            group = f"{h.run_id}-entity-{label}"
            await h.prime(ENTITY_REQUESTS, group)
            observer = await h.observer(ENTITY_RESPONSES)
            log = h.runtime / f"entity-{label}.jsonl"
            stream = log.open("w")
            command = [
                sys.executable,
                "-m",
                "src.kafka_service.worker",
                "--group-id",
                group,
            ]
            if label == "before":
                command.append("--no-idempotency")
            env = {
                **os.environ,
                "PYTHONPATH": f"{ROOT}:{ROOT / 'code'}",
                "HW8_SOURCE_COMMIT": h.source,
            }
            process = subprocess.Popen(
                command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT
            )
            h.processes.append((process, stream, log))
            await h.wait_event(log, "worker_ready")
            payload = {
                "correlation_id": str(uuid4()),
                "reply_to": ENTITY_RESPONSES,
                "operation": "CREATE_RENTAL",
                "data": RENTAL,
            }
            sends = []
            for _ in range(2):
                meta = await h.producer.send_and_wait(
                    ENTITY_REQUESTS, json.dumps(payload).encode()
                )
                sends.append(
                    {
                        "topic": meta.topic,
                        "partition": meta.partition,
                        "offset": meta.offset,
                        "payload": payload,
                    }
                )
            outputs = await h.collect(observer, {payload["correlation_id"]}, count=2)
            await h.wait_event(log, "response_sent", payload["correlation_id"])
            await asyncio.sleep(0.1)
            await h.stop(process)
            await observer.stop()
            rows = read_events(log)
            ids = [o["value"]["rental_id"] for o in outputs]
            count = max(r["rental_count"] for r in rows if "rental_count" in r)
            result = {
                "event": "observed_result",
                "responses": outputs,
                "sent": sends,
                "distinct_uuids": len(set(ids)),
                "rental_count": count,
                "correlation_id": payload["correlation_id"],
            }
            assert len(outputs) == 2 and count == (2 if label == "before" else 1)
            assert len(set(ids)) == count
            h.save("duplicate_" + label + ".jsonl", [result] + rows)
            summary[label] = {
                "rental_count": count,
                "distinct_uuids": len(set(ids)),
                "response_ids": ids,
            }
        h.save(
            "entity_duplicate_summary.json",
            {"source_commit": h.source, "run_id": h.run_id, **summary},
        )
        print(json.dumps(summary, indent=2))
    finally:
        await h.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    asyncio.run(run(p.parse_args()))
