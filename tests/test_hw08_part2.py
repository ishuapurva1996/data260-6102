"""Offline contract checks; broker/model evidence is collected separately."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from src.kafka_agents.common import StageProcessor
from src.kafka_agents.reliability import ReceiptStore


def task(cid="journey-1"):
    return {
        "correlation_id": cid,
        "run_id": "test",
        "rental_id": "rental-1",
        "sequence": 1,
        "question": "How does ordering affect rental updates?",
        "plan": "Explain ordering.",
    }


def test_receipt_reopen_preserves_output_and_publish_state(tmp_path):
    store = ReceiptStore(tmp_path / "writer.sqlite3")
    store.remember("abc", "fingerprint", {"draft": "original"})
    store.close()
    store = ReceiptStore(tmp_path / "writer.sqlite3")
    assert store.lookup("abc", "fingerprint") == ({"draft": "original"}, False)
    store.mark_published("abc")
    assert store.lookup("abc", "fingerprint") == ({"draft": "original"}, True)
    with pytest.raises(ValueError, match="different"):
        store.lookup("abc", "changed")
    store.close()


def test_attempt_budget_survives_restart(tmp_path):
    path = tmp_path / "writer.sqlite3"
    store = ReceiptStore(path)
    assert store.next_attempt("group/topic/0/1") == 1
    store.close()
    store = ReceiptStore(path)
    assert store.next_attempt("group/topic/0/1") == 2
    assert store.next_attempt("group/topic/0/1") == 3
    assert store.attempts("group/topic/0/1") == 3
    store.close()


class Producer:
    def __init__(self):
        self.sent = []

    async def send_and_wait(self, topic, value, **kwargs):
        self.sent.append((topic, json.loads(value)))
        return SimpleNamespace(topic=topic, partition=0, offset=len(self.sent) - 1)


class Consumer:
    def __init__(self):
        self.commits = []

    async def commit(self, offsets):
        self.commits.append(offsets)


def record(payload, offset=0):
    return SimpleNamespace(
        topic="s6102_tasks",
        partition=0,
        offset=offset,
        value=payload if isinstance(payload, bytes) else json.dumps(payload).encode(),
    )


def processor(tmp_path, baseline="reliable"):
    return StageProcessor(
        "writer",
        ReceiptStore(tmp_path / "writer.sqlite3"),
        model="fixture",
        baseline=baseline,
        group_id="tests",
        instance="writer-test",
        retry_backoff=0,
    )


def test_duplicate_has_one_logical_output_and_commits_both_records(tmp_path):
    async def run():
        stage, producer, consumer = processor(tmp_path), Producer(), Consumer()
        await stage.handle(record(task()), consumer, producer)
        await stage.handle(record(task(), 1), consumer, producer)
        assert len(producer.sent) == 1
        assert producer.sent[0][1]["correlation_id"] == "journey-1"
        assert producer.sent[0][1]["sequence"] == 1
        assert producer.sent[0][1]["draft"]
        assert [list(c.values())[0] for c in consumer.commits] == [1, 2]
        stage.store.close()

    asyncio.run(run())


def test_poison_three_attempts_then_dlq_and_next_record_succeeds(tmp_path):
    async def run():
        stage, producer, consumer = processor(tmp_path), Producer(), Consumer()
        await stage.handle(record(b"{not json"), consumer, producer)
        await stage.handle(record(task(), 1), consumer, producer)
        assert [x[0] for x in producer.sent] == ["s6102_dead_letter", "s6102_drafts"]
        dead = producer.sent[0][1]
        assert dead["attempts"] == 3
        assert dead["raw_utf8"] == "{not json"
        assert dead["source"] == {"topic": "s6102_tasks", "partition": 0, "offset": 0}
        assert [list(c.values())[0] for c in consumer.commits] == [1, 2]
        stage.store.close()

    asyncio.run(run())


def test_publish_failure_does_not_commit_and_cached_output_can_resume(tmp_path):
    class BrokenProducer(Producer):
        async def send_and_wait(self, *args, **kwargs):
            raise OSError("broker unavailable")

    async def run():
        stage, consumer = processor(tmp_path), Consumer()
        with pytest.raises(OSError):
            await stage.handle(record(task()), consumer, BrokenProducer())
        assert consumer.commits == []
        good = Producer()
        await stage.handle(record(task()), consumer, good)
        assert len(good.sent) == 1
        assert len(consumer.commits) == 1
        stage.store.close()

    asyncio.run(run())


def test_baseline_no_retry_stops_before_later_task(tmp_path):
    async def run():
        stage, producer, consumer = (
            processor(tmp_path, "no-retry"),
            Producer(),
            Consumer(),
        )
        with pytest.raises(ValueError):
            await stage.handle(record(b"{bad"), consumer, producer)
        assert producer.sent == []
        assert consumer.commits == []
        stage.store.close()

    asyncio.run(run())


def test_cached_output_recovers_after_publish_barrier_crash(tmp_path):
    async def run():
        stage, first, consumer = processor(tmp_path), Producer(), Consumer()
        stage.after_publish_delay = 60
        work = asyncio.create_task(stage.handle(record(task()), consumer, first))
        while not first.sent:
            await asyncio.sleep(0)
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await work
        assert consumer.commits == []
        assert len(first.sent) == 1
        stage.store.close()
        resumed, second = processor(tmp_path), Producer()
        await resumed.handle(record(task()), consumer, second)
        assert second.sent == first.sent
        assert len(consumer.commits) == 1
        resumed.store.close()

    asyncio.run(run())


def test_dlq_publish_failure_keeps_input_uncommitted_and_retry_budget(tmp_path):
    class BrokenProducer(Producer):
        async def send_and_wait(self, *args, **kwargs):
            raise OSError("broker unavailable")

    async def run():
        stage, consumer = processor(tmp_path), Consumer()
        with pytest.raises(OSError):
            await stage.handle(record(b"bad JSON"), consumer, BrokenProducer())
        assert consumer.commits == []
        assert stage.store.attempts("tests/s6102_tasks/0/0") == 3
        good = Producer()
        await stage.handle(record(b"bad JSON"), consumer, good)
        assert good.sent[0][1]["attempts"] == 3
        assert len(consumer.commits) == 1
        stage.store.close()

    asyncio.run(run())


def test_baseline_replay_creates_two_outputs(tmp_path):
    async def run():
        stage, producer, consumer = (
            processor(tmp_path, "no-dedup"),
            Producer(),
            Consumer(),
        )
        await stage.handle(record(task()), consumer, producer)
        await stage.handle(record(task(), 1), consumer, producer)
        assert len(producer.sent) == 2
        stage.store.close()

    asyncio.run(run())


def test_planner_and_reviewer_preserve_identity_and_final_answer(tmp_path):
    async def run():
        original = task()
        planner = StageProcessor(
            "planner", ReceiptStore(tmp_path / "planner.sqlite3"), model="fixture"
        )
        plan = await planner.generate({k: v for k, v in original.items() if k != "plan"})
        assert plan["correlation_id"] == original["correlation_id"]
        assert plan["question"] == original["question"]
        writer = processor(tmp_path)
        draft = await writer.generate(plan)
        reviewer = StageProcessor(
            "reviewer", ReceiptStore(tmp_path / "reviewer.sqlite3"), model="fixture"
        )
        final = await reviewer.generate(draft)
        assert final["correlation_id"] == original["correlation_id"]
        assert final["status"] == "approved"
        assert final["answer"] == draft["draft"]
        assert final["rental_id"] == original["rental_id"]
        for stage in (planner, writer, reviewer):
            stage.store.close()

    asyncio.run(run())
