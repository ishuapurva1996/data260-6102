"""Submit one question and read its correlated final result through Kafka."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from src.kafka_agents.common import wait_assignment
from src.kafka_service.config import FINAL, INBOX, PREFIX, KafkaSettings
from src.kafka_service.logging import event


async def send_question(
    question, *, run_id=None, correlation_id=None, timeout=180, rental_id=None
):
    settings = KafkaSettings.from_env()
    identity = correlation_id or str(uuid4())
    payload = {
        "correlation_id": identity,
        "run_id": run_id or f"question-{identity}",
        "question": question,
    }
    if rental_id is not None:
        payload["rental_id"] = rental_id
    consumer = AIOKafkaConsumer(
        FINAL,
        bootstrap_servers=settings.bootstrap_servers,
        group_id=f"{PREFIX}_result_{uuid4()}",
        enable_auto_commit=False,
        auto_offset_reset="latest",
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.bootstrap_servers, enable_idempotence=True
    )
    try:
        await consumer.start()
        await producer.start()
        await wait_assignment(consumer, settings.assignment_timeout)
        # Resolve a concrete tail before publication; old final records cannot be
        # mistaken for this question, even when the topic already contains work.
        await consumer.seek_to_end()
        sent = await producer.send_and_wait(
            INBOX, json.dumps(payload).encode(), key=str(rental_id or identity).encode()
        )
        event(
            "question_sent",
            topic=sent.topic,
            partition=sent.partition,
            offset=sent.offset,
            correlation_id=identity,
            run_id=payload["run_id"],
            payload=payload,
        )
        async with asyncio.timeout(timeout):
            async for record in consumer:
                result = json.loads(record.value)
                if result.get("correlation_id") != identity:
                    continue
                if (
                    not isinstance(result.get("answer"), str)
                    or not result["answer"].strip()
                    or not result.get("status")
                ):
                    raise ValueError("Final result is missing status or answer")
                event(
                    "final_received",
                    topic=record.topic,
                    partition=record.partition,
                    offset=record.offset,
                    correlation_id=identity,
                    run_id=payload["run_id"],
                    final=result,
                )
                return {
                    "request": payload,
                    "final": result,
                    "sent": {
                        "topic": sent.topic,
                        "partition": sent.partition,
                        "offset": sent.offset,
                    },
                    "received": {
                        "topic": record.topic,
                        "partition": record.partition,
                        "offset": record.offset,
                    },
                }
    finally:
        await consumer.stop()
        await producer.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "question",
        nargs="?",
        default="How does Kafka message ordering affect updates to the same rental listing?",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--correlation-id")
    parser.add_argument("--rental-id")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        send_question(
            args.question,
            run_id=args.run_id,
            correlation_id=args.correlation_id,
            timeout=args.timeout,
            rental_id=args.rental_id,
        )
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["final"], indent=2))


if __name__ == "__main__":
    main()
