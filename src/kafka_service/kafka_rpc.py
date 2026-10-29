"""Async pending-future Kafka RPC; caller identity survives the complete journey."""

import asyncio
import contextlib
import json
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import ValidationError

from .config import ENTITY_REQUESTS, ENTITY_RESPONSES, PREFIX, KafkaSettings
from .logging import event
from .schemas import RentalRequest, clean_validation_error, error_response


class KafkaRPC:
    def __init__(
        self, settings=None, *, producer_factory=AIOKafkaProducer, consumer_factory=AIOKafkaConsumer
    ):
        self.settings = settings or KafkaSettings.from_env()
        self.producer_factory = producer_factory
        self.consumer_factory = consumer_factory
        self.producer = None
        self.consumer = None
        self.pending = {}
        self.response_task = None
        self.started = False

    async def start(self):
        if self.started:
            return
        # aiokafka clients must be constructed inside their running event loop.
        self.producer = self.producer_factory(
            bootstrap_servers=self.settings.bootstrap_servers, enable_idempotence=True
        )
        self.consumer = self.consumer_factory(
            ENTITY_RESPONSES,
            bootstrap_servers=self.settings.bootstrap_servers,
            group_id=f"{PREFIX}_rpc_{uuid4().hex}",
            auto_offset_reset="latest",
            enable_auto_commit=False,
        )
        try:
            await self.producer.start()
            await self.consumer.start()
            async with asyncio.timeout(self.settings.assignment_timeout):
                while not self.consumer.assignment():
                    await self.consumer.getmany(timeout_ms=100)
            self.started = True
            self.response_task = asyncio.create_task(self._consume_responses())
            event("rpc_ready", stage="rpc", topic=ENTITY_RESPONSES)
        except BaseException:
            await self.stop()
            raise

    async def stop(self):
        self.started = False
        for (correlation_id, operation), future in list(self.pending.items()):
            if not future.done():
                future.set_result(
                    error_response(
                        {"correlation_id": correlation_id, "operation": operation},
                        "Kafka RPC stopped",
                        transport=True,
                    )
                )
        self.pending.clear()
        if self.response_task is not None:
            self.response_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.response_task
            self.response_task = None
        if self.consumer is not None:
            await self.consumer.stop()
            self.consumer = None
        if self.producer is not None:
            await self.producer.stop()
            self.producer = None

    async def _consume_responses(self):
        try:
            async for record in self.consumer:
                try:
                    response = json.loads(record.value.decode())
                    if not isinstance(response, dict) or type(response.get("success")) is not bool:
                        raise ValueError("Response must contain Boolean success")
                    key = (response.get("correlation_id"), response.get("operation"))
                    future = self.pending.get(key)
                except (ValueError, UnicodeDecodeError, TypeError):
                    event(
                        "response_rejected",
                        stage="rpc",
                        topic=record.topic,
                        partition=record.partition,
                        offset=record.offset,
                    )
                    continue
                event(
                    "response_received",
                    stage="rpc",
                    topic=record.topic,
                    partition=record.partition,
                    offset=record.offset,
                    response=response,
                    correlation_id=key[0],
                    operation=key[1],
                    matched=future is not None,
                )
                if future is not None and not future.done():
                    future.set_result(response)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.started = False
            event("response_consumer_failed", stage="rpc", error=type(exc).__name__)
            for key, future in list(self.pending.items()):
                if not future.done():
                    future.set_result(
                        error_response(
                            {"correlation_id": key[0], "operation": key[1]},
                            "Kafka response consumer failed",
                            transport=True,
                        )
                    )

    async def make_request(self, payload: dict) -> dict:
        try:
            envelope = RentalRequest.model_validate(payload).model_dump()
        except ValidationError as exc:
            return error_response(payload, clean_validation_error(exc))
        if not self.started:
            return error_response(payload, "Kafka RPC is not ready", transport=True)
        key = (envelope["correlation_id"], envelope["operation"])
        if key in self.pending:
            return error_response(payload, "This correlation ID and operation are already pending")
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future  # Register before a fast worker can reply.
        try:
            async with asyncio.timeout(self.settings.rpc_timeout):
                event(
                    "request_sending",
                    stage="rpc",
                    topic=ENTITY_REQUESTS,
                    message=envelope,
                    correlation_id=key[0],
                    operation=key[1],
                )
                sent = await self.producer.send_and_wait(
                    ENTITY_REQUESTS, json.dumps(envelope).encode()
                )
                event(
                    "request_sent",
                    stage="rpc",
                    topic=sent.topic,
                    partition=sent.partition,
                    offset=sent.offset,
                    correlation_id=key[0],
                    operation=key[1],
                )
                response = await future
                event(
                    "response_returned",
                    stage="rpc",
                    correlation_id=key[0],
                    operation=key[1],
                    response=response,
                )
                return response
        except TimeoutError:
            return error_response(payload, "Kafka request timed out", transport=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            event(
                "request_send_failed",
                stage="rpc",
                correlation_id=key[0],
                operation=key[1],
                error=type(exc).__name__,
            )
            return error_response(payload, "Kafka request transport failed", transport=True)
        finally:
            self.pending.pop(key, None)
            if not future.done():
                future.cancel()
