"""Offline HW8 contracts; real Kafka experiments are coordinator-owned."""

import asyncio
import copy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.kafka_service.config import ENTITY_RESPONSES, KafkaSettings
from src.kafka_service.kafka_rpc import KafkaRPC
from src.kafka_service.worker import RentalWorker

PAYLOAD = {
    "listingTitle": "HW8 synthetic apartment",
    "propertyAddress": "100 Example Street, San Jose, CA",
    "submitterEmail": "hw8@example.com",
    "description": "Synthetic listing used only to verify the Kafka assignment.",
    "propertyType": "apartment",
    "termsAccepted": True,
}


def request(operation="CREATE_RENTAL", data=None, correlation_id="journey-6102"):
    return {
        "correlation_id": correlation_id,
        "reply_to": ENTITY_RESPONSES,
        "operation": operation,
        "data": copy.deepcopy(PAYLOAD if data is None else data),
    }


def test_roundtrip_replay_and_sequential_get_share_correlation():
    worker = RentalWorker()
    created = worker.process_request(request())
    assert created["success"] and UUID(created["rental_id"]).version == 4
    assert worker.process_request(request()) == created
    assert len(worker.rentals) == 1
    got = worker.process_request(request("GET_RENTAL", {"rental_id": created["rental_id"]}))
    assert got["success"] and got["correlation_id"] == created["correlation_id"]
    assert all(got["rental"][k] == v for k, v in PAYLOAD.items())
    changed = worker.process_request(request(data={**PAYLOAD, "listingTitle": "Different"}))
    assert not changed["success"] and len(worker.rentals) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"listingTitle": ""},
        {"propertyAddress": " "},
        {"submitterEmail": "invalid"},
        {"description": "too short"},
        {"propertyType": "boat"},
        {"termsAccepted": False},
        {"termsAccepted": "true"},
        {"availableUnits": -1},
        {"listingTitle": None},
    ],
)
def test_invalid_domain_fields_preserve_correlation_and_do_not_create(changes):
    worker = RentalWorker()
    result = worker.process_request(request(data={**PAYLOAD, **changes}))
    assert result["success"] is False and result["correlation_id"] == "journey-6102"
    assert result["error"] and not worker.rentals


@pytest.mark.parametrize("field", list(PAYLOAD))
def test_every_required_field_is_required(field):
    data = PAYLOAD.copy()
    data.pop(field)
    assert RentalWorker().process_request(request(data=data))["success"] is False


def test_unknown_operation_and_unknown_or_invalid_id_are_clean_errors():
    worker = RentalWorker()
    for message in (
        request("DELETE_RENTAL", {}),
        request("GET_RENTAL", {"rental_id": str(uuid4())}),
        request("GET_RENTAL", {"rental_id": "not-a-uuid"}),
        {**request(), "data": []},
        {**request(), "reply_to": "other_topic"},
    ):
        result = worker.process_request(message)
        assert result["success"] is False and result["error"]
        assert result["correlation_id"] == message["correlation_id"]


def test_explicit_duplicate_baseline_creates_twice():
    worker = RentalWorker(idempotency=False)
    first, second = worker.process_request(request()), worker.process_request(request())
    assert first["rental_id"] != second["rental_id"] and len(worker.rentals) == 2


class ResponseConsumer:
    def __init__(self, *args, **kwargs):
        self.queue = asyncio.Queue()
        self.stopped = False

    async def start(self):
        pass

    def assignment(self):
        return {("responses", 0)}

    async def stop(self):
        self.stopped = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        value = await self.queue.get()
        return SimpleNamespace(value=value, topic=ENTITY_RESPONSES, partition=0, offset=0)


class ResponseProducer:
    def __init__(self, *args, **kwargs):
        self.rpc = None
        self.mode = "normal"
        self.stopped = False
        self.sent = asyncio.Event()

    async def start(self):
        pass

    async def stop(self):
        self.stopped = True

    async def send_and_wait(self, topic, value):
        payload = __import__("json").loads(value)
        self.sent.set()
        if self.mode == "fail":
            raise OSError("simulated send failure")
        if self.mode == "normal":
            # A stale CREATE cannot satisfy a pending GET using the journey ID.
            stale = {
                "correlation_id": payload["correlation_id"],
                "operation": "CREATE_RENTAL",
                "success": True,
                "rental_id": "stale-create",
            }
            wanted = {
                **stale,
                "operation": payload["operation"],
                "rental": {"rental_id": "correct"},
            }
            if payload["operation"] == "GET_RENTAL":
                await self.rpc.consumer.queue.put(__import__("json").dumps(stale).encode())
            await self.rpc.consumer.queue.put(__import__("json").dumps(wanted).encode())
        return SimpleNamespace(topic=topic, partition=0, offset=1)


def make_rpc(timeout=0.03):
    rpc = KafkaRPC(
        KafkaSettings(rpc_timeout=timeout),
        producer_factory=ResponseProducer,
        consumer_factory=ResponseConsumer,
    )
    return rpc


def test_rpc_preserves_full_response_and_does_not_match_other_operation():
    async def check():
        rpc = make_rpc()
        await rpc.start()
        rpc.producer.rpc = rpc
        result = await rpc.make_request(request("GET_RENTAL", {"rental_id": str(uuid4())}))
        assert result["success"] and result["operation"] == "GET_RENTAL"
        assert result["rental"]["rental_id"] == "correct"
        assert not rpc.pending
        await rpc.stop()

    asyncio.run(check())


@pytest.mark.parametrize("mode", ["timeout", "fail", "cancel", "stop"])
def test_rpc_cleans_pending_on_every_transport_exit(mode):
    async def check():
        rpc = make_rpc()
        await rpc.start()
        rpc.producer.rpc = rpc
        rpc.producer.mode = mode
        task = asyncio.create_task(rpc.make_request(request()))
        await rpc.producer.sent.wait()
        if mode == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            if mode == "stop":
                await rpc.stop()
            result = await task
            assert result["success"] is False and result["transport_error"]
            assert result["correlation_id"] == "journey-6102"
        assert not rpc.pending
        await rpc.stop()

    asyncio.run(check())


def test_wrapper_preserves_auth_and_roles_and_lifecycle(monkeypatch):
    from fastapi import HTTPException
    from web_application.main import create_app
    from web_application.routers.auth import require_user

    class RPC:
        def __init__(self):
            self.calls = []
            self.started = self.stopped = False

        async def start(self):
            self.started = True

        async def stop(self):
            self.stopped = True

        async def make_request(self, payload):
            self.calls.append(payload)
            return {
                "correlation_id": payload["correlation_id"],
                "operation": payload["operation"],
                "success": True,
            }

    monkeypatch.setenv("HW7_JWT_SECRET", "test-only-6102-" + "x" * 40)
    rpc = RPC()
    app = create_app(kafka_rpc=rpc)
    with TestClient(app) as client:
        assert rpc.started

        # An authentication dependency failure cannot reach Kafka.
        def denied():
            raise HTTPException(401, "Authentication required")

        app.dependency_overrides[require_user] = denied
        assert client.post("/api/kafka/rentals", json=request()).status_code == 401
        assert not rpc.calls
        app.dependency_overrides[require_user] = lambda: SimpleNamespace(role="reader")
        assert client.post("/api/kafka/rentals", json=request()).status_code == 403
        assert not rpc.calls
        got = client.post(
            "/api/kafka/rentals", json=request("GET_RENTAL", {"rental_id": str(uuid4())})
        )
        assert got.status_code == 200 and got.json()["correlation_id"] == "journey-6102"
        app.dependency_overrides[require_user] = lambda: SimpleNamespace(role="writer")
        assert client.post("/api/kafka/rentals", json=request()).status_code == 200
        assert len(rpc.calls) == 2
    assert rpc.stopped
