"""Single dictionary rental worker, adapted from the instructor's async demo."""

import argparse
import asyncio
import copy
import hashlib
import json
import os
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from pydantic import ValidationError

from .config import ENTITY_REQUESTS, ENTITY_RESPONSES, PREFIX, KafkaSettings
from .logging import event
from .schemas import (
    RentalRequest,
    clean_validation_error,
    error_response,
    validate_data,
)


class RentalWorker:
    def __init__(self, *, idempotency=True):
        self.rentals = {}  # Assignment requirement: worker-local plain Python dictionary.
        self.responses = {}
        self.idempotency = idempotency

    def process_request(self, payload) -> dict:
        try:
            envelope = RentalRequest.model_validate(payload)
            data = validate_data(envelope.operation, envelope.data)
        except ValidationError as exc:
            return error_response(payload, clean_validation_error(exc))
        except ValueError as exc:
            return error_response(payload, str(exc))

        identity = (envelope.operation, envelope.correlation_id)
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        if self.idempotency and identity in self.responses:
            original_fingerprint, response = self.responses[identity]
            if original_fingerprint != fingerprint:
                return error_response(payload, "Correlation ID already used with different data")
            event(
                "duplicate_cached",
                stage="entity_worker",
                operation=envelope.operation,
                correlation_id=envelope.correlation_id,
                rental_count=len(self.rentals),
                response=response,
            )
            return copy.deepcopy(response)

        response = {
            "correlation_id": envelope.correlation_id,
            "operation": envelope.operation,
            "success": True,
        }
        if envelope.operation == "CREATE_RENTAL":
            rental_id = str(uuid4())
            self.rentals[rental_id] = {"rental_id": rental_id, **data}
            response.update(rental_id=rental_id, message="Rental created")
        else:
            rental = self.rentals.get(data["rental_id"])
            if rental is None:
                return error_response(payload, "Rental not found")
            response["rental"] = copy.deepcopy(rental)

        if self.idempotency:
            self.responses[identity] = (fingerprint, copy.deepcopy(response))
        event(
            "request_processed",
            stage="entity_worker",
            operation=envelope.operation,
            correlation_id=envelope.correlation_id,
            rental_count=len(self.rentals),
            response=response,
        )
        return response


async def run_worker(*, group_id=f"{PREFIX}_entity_worker", idempotency=True):
    settings = KafkaSettings.from_env()
    consumer = AIOKafkaConsumer(
        ENTITY_REQUESTS,
        bootstrap_servers=settings.bootstrap_servers,
        group_id=group_id,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.bootstrap_servers, enable_idempotence=True
    )
    worker = RentalWorker(idempotency=idempotency)
    try:
        await producer.start()
        await consumer.start()
        async with asyncio.timeout(settings.assignment_timeout):
            while not consumer.assignment():
                await asyncio.sleep(0.05)
        event(
            "worker_ready",
            stage="entity_worker",
            group_id=group_id,
            topic=ENTITY_REQUESTS,
            idempotency=idempotency,
            assignments=[
                {"topic": tp.topic, "partition": tp.partition}
                for tp in sorted(consumer.assignment())
            ],
            message="Consumer is ready and listening...",
        )
        async for record in consumer:
            metadata = {
                "topic": record.topic,
                "partition": record.partition,
                "offset": record.offset,
                "stage": "entity_worker",
            }
            try:
                payload = json.loads(record.value.decode())
            except (ValueError, UnicodeDecodeError):
                event(
                    "malformed_record",
                    **metadata,
                    error="Invalid UTF-8 JSON",
                    raw_hex=record.value.hex(),
                )
                payload = None
            else:
                event("request_received", **metadata, message=payload)

            if isinstance(payload, dict) and isinstance(payload.get("correlation_id"), str):
                response = worker.process_request(payload)
                # Invalid reply destinations receive their clean error on the one allowed topic.
                reply_to = payload.get("reply_to")
                if reply_to != ENTITY_RESPONSES:
                    reply_to = ENTITY_RESPONSES
                sent = await producer.send_and_wait(reply_to, json.dumps(response).encode())
                event(
                    "response_sent",
                    **metadata,
                    correlation_id=response["correlation_id"],
                    operation=response["operation"],
                    response=response,
                    response_topic=sent.topic,
                    response_partition=sent.partition,
                    response_offset=sent.offset,
                    rental_count=len(worker.rentals),
                )
            elif payload is not None:
                event(
                    "malformed_record",
                    **metadata,
                    error="No usable correlation_id",
                    message=payload,
                )

            # Publication acknowledgement precedes the successful commit.
            await consumer.commit(
                {TopicPartition(record.topic, record.partition): record.offset + 1}
            )
            event("offset_committed", **metadata, committed_offset=record.offset + 1)
    finally:
        await consumer.stop()
        await producer.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--group-id", default=os.getenv("HW8_ENTITY_GROUP", f"{PREFIX}_entity_worker")
    )
    parser.add_argument(
        "--no-idempotency",
        action="store_true",
        help="Explicit before-fix duplicate experiment only",
    )
    args = parser.parse_args()
    asyncio.run(run_worker(group_id=args.group_id, idempotency=not args.no_idempotency))


if __name__ == "__main__":
    main()
