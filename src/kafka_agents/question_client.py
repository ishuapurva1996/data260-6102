"""Publish a question and await its correlated HW8 final record."""

import asyncio
import json
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from src.kafka_service.config import FINAL, INBOX, PREFIX, KafkaSettings
from src.kafka_service.logging import event, utc_now

from .common import wait_assignment
from .transport import coordinates, send_traced, trace_receipt


async def send_question(
    question,
    *,
    run_id=None,
    correlation_id=None,
    timeout=180,
    rental_id=None,
    rental_context=None,
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
    if rental_context is not None:
        payload["rental_context"] = rental_context
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
        sent, timing = await send_traced(
            producer, INBOX, payload, key=str(rental_id or identity).encode()
        )
        event(
            "question_sent",
            **coordinates(sent),
            **timing,
            correlation_id=identity,
            run_id=payload["run_id"],
            payload=payload,
        )
        async with asyncio.timeout(timeout):
            async for record in consumer:
                received = utc_now()
                result = json.loads(record.value)
                if result.get("correlation_id") != identity:
                    continue
                if (
                    not isinstance(result.get("answer"), str)
                    or not result["answer"].strip()
                    or not result.get("status")
                ):
                    error = "Final result is missing status or answer"
                    trace_receipt(record, identity, received, error=error)
                    raise ValueError(error)
                trace_receipt(record, identity, received)
                event(
                    "final_received",
                    **coordinates(record),
                    receive_time=received.isoformat(),
                    correlation_id=identity,
                    run_id=payload["run_id"],
                    final=result,
                )
                return {
                    "request": payload,
                    "final": result,
                    "sent": coordinates(sent),
                    "received": coordinates(record),
                }
    finally:
        await consumer.stop()
        await producer.stop()
