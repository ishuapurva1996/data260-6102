#!/usr/bin/env python3
"""Coordinator-only real Kafka failure runs. Fixture prose isolates transport behavior.

Run after stopping other pipeline processes. Fresh group offsets are explicitly primed
to the current topic ends; restart cases keep the same group and durable receipts.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition

from src.kafka_service.config import (
    DEAD_LETTER,
    DRAFTS,
    FINAL,
    TASKS,
    VERIFY_SEED,
    KafkaSettings,
)
from src.kafka_service.logging import event


def read_events(path):
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


class Harness:
    def __init__(self, runtime, output):
        self.runtime, self.output = runtime, output
        self.run_id = "hw8-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)
        self.processes = []
        self.bootstrap = KafkaSettings.from_env().bootstrap_servers
        self.source = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()

    async def start(self):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap, enable_idempotence=True
        )
        await self.producer.start()

    async def prime(self, topic, group):
        c = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap,
            group_id=group,
            enable_auto_commit=False,
            auto_offset_reset="latest",
        )
        await c.start()
        try:
            async with asyncio.timeout(30):
                while not c.assignment():
                    await c.getmany(timeout_ms=100)
            ends = await c.end_offsets(c.assignment())
            await c.commit(ends)
            event(
                "experiment_group_primed",
                group=group,
                offsets={f"{tp.topic}:{tp.partition}": n for tp, n in ends.items()},
            )
        finally:
            await c.stop()

    async def observer(self, topic):
        c = AIOKafkaConsumer(bootstrap_servers=self.bootstrap, enable_auto_commit=False)
        await c.start()
        parts = c.partitions_for_topic(topic)
        if parts is None:
            await c._client.force_metadata_update()
            parts = c.partitions_for_topic(topic)
        c.assign([TopicPartition(topic, p) for p in sorted(parts)])
        await c.seek_to_end()
        return c

    def spawn(
        self,
        label,
        group,
        state,
        baseline="reliable",
        instance=None,
        after_publish=0,
        model="fixture",
    ):
        log = self.runtime / f"{label}-{uuid4().hex[:6]}.jsonl"
        stream = log.open("w")
        stage = label.split("-")[0]
        cmd = [
            sys.executable,
            str(ROOT / "scripts/hw08" / f"{stage}.py"),
            "--state-dir",
            str(self.runtime / state),
            "--group-id",
            group,
            "--model",
            model,
            "--instance",
            instance or label,
            "--baseline",
            baseline,
            "--after-publish-delay",
            str(after_publish),
        ]
        env = {
            **os.environ,
            "PYTHONPATH": f"{ROOT}:{ROOT / 'code'}",
            "HW8_SOURCE_COMMIT": self.source,
            "PYTHONUNBUFFERED": "1",
        }
        process = subprocess.Popen(
            cmd, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT
        )
        self.processes.append((process, stream, log))
        event(
            "experiment_process_started",
            command=cmd,
            child_pid=process.pid,
            log=str(log),
        )
        return process, log

    async def wait_event(self, path, name, cid=None, timeout=35):
        async with asyncio.timeout(timeout):
            while True:
                for row in read_events(path):
                    if row.get("event") == name and (
                        cid is None or row.get("correlation_id") == cid
                    ):
                        return row
                await asyncio.sleep(0.05)

    async def stop(self, process, sig=signal.SIGTERM):
        if process.poll() is None:
            process.send_signal(sig)
            async with asyncio.timeout(10):
                while process.poll() is None:
                    await asyncio.sleep(0.05)
        event(
            "experiment_process_stopped",
            child_pid=process.pid,
            exit_code=process.returncode,
            signal=sig.name,
        )

    async def send(self, payload, partition=None, key=None, raw=None):
        metadata = await self.producer.send_and_wait(
            TASKS,
            raw if raw is not None else json.dumps(payload).encode(),
            partition=partition,
            key=key,
        )
        row = event(
            "experiment_sent",
            payload=payload,
            topic=metadata.topic,
            partition=metadata.partition,
            offset=metadata.offset,
            key=key.decode() if key else None,
        )
        return row

    async def collect(self, consumer, ids, timeout=15, count=None):
        rows = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            batches = await consumer.getmany(timeout_ms=200)
            for records in batches.values():
                for record in records:
                    value = json.loads(record.value)
                    if value.get("correlation_id") in ids:
                        rows.append(
                            {
                                "observed_at": datetime.now(timezone.utc).isoformat(),
                                "topic": record.topic,
                                "partition": record.partition,
                                "offset": record.offset,
                                "value": value,
                            }
                        )
            if count is not None and len(rows) >= count:
                return rows
        return rows

    def task(self, suffix, **extra):
        return {
            "correlation_id": f"{self.run_id}-{suffix}-{uuid4().hex[:6]}",
            "run_id": self.run_id,
            "rental_id": "synthetic-rental-6102",
            "question": "Explain how ordering affects rental listing updates.",
            "plan": "Use the listing key and explain per-partition ordering.",
            **extra,
        }

    def save(self, name, rows):
        path = self.output / name
        if name.endswith(".jsonl"):
            path.write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
            )
        else:
            path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")

    async def duplicate(self, baseline):
        label = "before" if baseline else "after"
        group = f"{self.run_id}-duplicate-{label}"
        review_group = group + "-reviewer"
        await self.prime(TASKS, group)
        await self.prime(DRAFTS, review_group)
        observer = await self.observer(FINAL)
        mode = "no-dedup" if baseline else "reliable"
        reviewer, review_log = self.spawn(
            "reviewer-duplicate-" + label,
            review_group,
            "dup-review-" + label,
            baseline=mode,
        )
        writer, writer_log = self.spawn(
            "writer-duplicate-" + label, group, "dup-write-" + label, baseline=mode
        )
        await self.wait_event(review_log, "consumer_ready")
        await self.wait_event(writer_log, "consumer_ready")
        payload = self.task("duplicate-" + label)
        first = await self.send(payload, partition=0)
        await self.wait_event(writer_log, "offset_committed", payload["correlation_id"])
        second = await self.send(payload, partition=0)
        outputs = await self.collect(
            observer, {payload["correlation_id"]}, timeout=4, count=None
        )
        await self.stop(writer)
        await self.stop(reviewer)
        await observer.stop()
        rows = [first, second, {"event": "observed_result", "final_outputs": outputs}]
        rows += read_events(writer_log) + read_events(review_log)
        self.save(f"pipeline_duplicate_{label}.jsonl", rows)
        assert len(outputs) == (2 if baseline else 1)
        return {
            "final_outputs": len(outputs),
            "correlation_id": payload["correlation_id"],
        }

    async def boundary(self):
        group = f"{self.run_id}-boundary"
        await self.prime(TASKS, group)
        await self.prime(DRAFTS, group + "-reviewer")
        observer = await self.observer(FINAL)
        reviewer, rl = self.spawn(
            "reviewer-boundary", group + "-reviewer", "boundary-review"
        )
        writer, wl = self.spawn(
            "writer-boundary", group, "boundary-write", after_publish=2
        )
        await self.wait_event(rl, "consumer_ready")
        await self.wait_event(wl, "consumer_ready")
        payload = self.task("publish-boundary")
        sent = await self.send(payload, partition=0)
        barrier = await self.wait_event(
            wl, "after_publish_barrier", payload["correlation_id"]
        )
        await self.stop(writer, signal.SIGKILL)
        restarted, rwl = self.spawn("writer-boundary-restart", group, "boundary-write")
        await self.wait_event(rwl, "consumer_ready")
        await self.wait_event(rwl, "offset_committed", payload["correlation_id"])
        outputs = await self.collect(
            observer, {payload["correlation_id"]}, timeout=3, count=None
        )
        await self.stop(restarted)
        await self.stop(reviewer)
        await observer.stop()
        rows = [sent, barrier, {"event": "observed_result", "final_outputs": outputs}]
        rows += read_events(wl) + read_events(rwl) + read_events(rl)
        self.save("publish_commit_boundary.jsonl", rows)
        assert len(outputs) == 1
        assert any(r.get("event") == "duplicate_cached" for r in read_events(rwl))
        return {"final_outputs": len(outputs), "cached_on_restart": True}

    async def death(self, baseline):
        label = "before" if baseline else "after"
        group = f"{self.run_id}-death-{label}"
        await self.prime(TASKS, group)
        observer = await self.observer(DRAFTS)
        process, log = self.spawn(
            "writer-death-" + label,
            group,
            "death-" + label,
            baseline="early-commit" if baseline else "reliable",
        )
        await self.wait_event(log, "consumer_ready")
        payload = self.task("death-" + label, delay_seconds=1.0)
        sent = await self.send(payload, partition=0)
        started = await self.wait_event(
            log, "processing_started", payload["correlation_id"]
        )
        await self.stop(process, signal.SIGKILL)
        restarted, restart_log = self.spawn(
            "writer-restart-" + label, group, "death-" + label
        )
        await self.wait_event(restart_log, "consumer_ready")
        outputs = await self.collect(
            observer,
            {payload["correlation_id"]},
            timeout=4 if baseline else 15,
            count=None if baseline else 1,
        )
        await self.stop(restarted)
        await observer.stop()
        rows = [
            sent,
            started,
            {
                "event": "observed_result",
                "outputs": outputs,
                "bounded_observation_seconds": 4 if baseline else 15,
                "killed_pid": process.pid,
                "restart_pid": restarted.pid,
            },
        ]
        rows += read_events(log) + read_events(restart_log)
        self.save(f"consumer_death_{label}.jsonl", rows)
        assert len(outputs) == (0 if baseline else 1), rows
        return {
            "outputs": len(outputs),
            "killed_pid": process.pid,
            "restart_pid": restarted.pid,
            "input_partition": sent["partition"],
            "input_offset": sent["offset"],
        }

    async def poison(self, baseline):
        label = "before" if baseline else "after"
        group = f"{self.run_id}-poison-{label}"
        await self.prime(TASKS, group)
        observer, dlq = await self.observer(DRAFTS), await self.observer(DEAD_LETTER)
        process, log = self.spawn(
            "writer-poison-" + label,
            group,
            "poison-" + label,
            baseline="no-retry" if baseline else "reliable",
        )
        await self.wait_event(log, "consumer_ready")
        bad, good = self.task("poison-" + label), self.task("later-" + label)
        bad["plan"] = None
        sent_bad = await self.send(bad, partition=0)
        sent_good = await self.send(good, partition=0)
        outputs = await self.collect(
            observer,
            {good["correlation_id"]},
            timeout=4 if baseline else 15,
            count=None if baseline else 1,
        )
        dead = await self.collect(dlq, {bad["correlation_id"]}, timeout=1, count=None)
        await self.stop(process)
        await observer.stop()
        await dlq.stop()
        rows = [
            sent_bad,
            sent_good,
            {
                "event": "observed_result",
                "later_outputs": outputs,
                "dead_letters": dead,
                "exit_code": process.returncode,
            },
        ]
        rows += read_events(log)
        self.save(f"poison_{label}.jsonl", rows)
        assert len(outputs) == (0 if baseline else 1)
        assert len(dead) == (0 if baseline else 1)
        return {
            "later_outputs": len(outputs),
            "dead_letters": len(dead),
            "exit_code": process.returncode,
        }

    async def ordering(self):
        rng = random.Random(VERIFY_SEED)
        delays = [
            round(rng.uniform(0.02, 0.08) + (0.20 if n % 2 == 1 else 0), 4)
            for n in range(1, 21)
        ]
        manifest = {
            "verify_seed": VERIFY_SEED,
            "run_id": self.run_id,
            "messages": [],
            "unkeyed_distribution": "controlled explicit alternating partition; no key",
        }
        results = {}
        for mode in ("unkeyed", "keyed"):
            group = f"{self.run_id}-ordering-{mode}"
            await self.prime(TASKS, group)
            observer = await self.observer(DRAFTS)
            p1, l1 = self.spawn(
                "writer-order-" + mode, group, "order-" + mode, instance="writer-A"
            )
            await self.wait_event(l1, "consumer_ready")
            p2, l2 = self.spawn(
                "writer-order-" + mode, group, "order-" + mode, instance="writer-B"
            )
            await self.wait_event(l2, "consumer_ready")
            # Wait for the two-member rebalance to settle before publishing.
            await asyncio.sleep(2)
            sent = {}
            for sequence, delay in enumerate(delays, 1):
                payload = self.task(
                    f"{mode}-{sequence}", sequence=sequence, delay_seconds=delay
                )
                meta = await self.send(
                    payload,
                    partition=(sequence - 1) % 2 if mode == "unkeyed" else None,
                    key=payload["rental_id"].encode() if mode == "keyed" else None,
                )
                sent[payload["correlation_id"]] = meta
                manifest["messages"].append(
                    {
                        "mode": mode,
                        **payload,
                        "partition": meta["partition"],
                        "offset": meta["offset"],
                    }
                )
            outputs = await self.collect(observer, set(sent), timeout=35, count=20)
            await self.stop(p1)
            await self.stop(p2)
            await observer.stop()
            events = read_events(l1) + read_events(l2)
            self.save(f"ordering_{mode}_events.jsonl", events)
            rows = []
            for order, out in enumerate(outputs, 1):
                value = out["value"]
                cid = value["correlation_id"]
                matching = [
                    e
                    for e in events
                    if e.get("correlation_id") == cid
                    and e.get("event") == "processing_started"
                ]
                rows.append(
                    {
                        "observed_order": order,
                        "sequence": value["sequence"],
                        "correlation_id": cid,
                        "task_partition": sent[cid]["partition"],
                        "task_offset": sent[cid]["offset"],
                        "draft_offset": out["offset"],
                        "instance": matching[0].get("instance") if matching else "",
                        "observed_at": out["observed_at"],
                        "delay_seconds": value["delay_seconds"],
                    }
                )
            with (self.output / f"ordering_{mode}.csv").open("w") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            sequences = [r["sequence"] for r in rows]
            assert len(rows) == len(set(sequences)) == 20
            assert set(sequences) == set(range(1, 21))
            parts = sorted({r["task_partition"] for r in rows})
            if mode == "keyed":
                assert len(parts) == 1 and sequences == list(range(1, 21))
            results[mode] = {
                "count": len(rows),
                "partitions": parts,
                "observed_sequences": sequences,
                "in_send_order": sequences == list(range(1, 21)),
            }
        self.save("ordering_manifest.json", manifest)
        return results

    async def close(self):
        for process, stream, _ in self.processes:
            if process.poll() is None:
                await self.stop(process)
            stream.close()
        await self.producer.stop()


async def main(args):
    harness = Harness(args.runtime_dir, args.output_dir)
    await harness.start()
    summary = {
        "run_id": harness.run_id,
        "source_commit": harness.source,
        "model": "fixture (transport experiments only)",
        "verify_seed": VERIFY_SEED,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if args.part in ("duplicate", "all"):
            summary["pipeline_duplicate"] = {
                "before": await harness.duplicate(True),
                "after": await harness.duplicate(False),
            }
            summary["publish_commit_boundary"] = await harness.boundary()
        if args.part in ("death", "all"):
            summary["consumer_death"] = {
                "before": await harness.death(True),
                "after": await harness.death(False),
            }
        if args.part in ("poison", "all"):
            summary["poison"] = {
                "before": await harness.poison(True),
                "after": await harness.poison(False),
            }
        if args.part in ("ordering", "all"):
            summary["ordering"] = await harness.ordering()
        summary["completed_at"] = datetime.now(timezone.utc).isoformat()
        harness.save("failure_summary.json", summary)
        event("experiments_completed", summary=summary)
    finally:
        await harness.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--part",
        choices=["all", "duplicate", "death", "poison", "ordering"],
        default="all",
    )
    asyncio.run(main(parser.parse_args()))
