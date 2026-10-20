"""In-process router/service checks with disposable BSON-backed fixtures, not live MongoDB."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bson import BSON, ObjectId
from bson.codec_options import CodecOptions
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pymongo.errors import CollectionInvalid, OperationFailure, ServerSelectionTimeoutError
import pytest

from src.hw06_documents.schemas import RentalCreate, RentalUpdate
from src.hw06_documents.service import DocumentService
from src.hw06_shared.errors import install_error_handlers
from web_application.routers.doc_rentals import create_router


class DisposableCollection:
    """Only the PyMongo calls used by the service; BSON roundtrips preserve storage precision."""
    def __init__(self):
        self.documents = {}
        self.failure = None

    def check(self):
        if self.failure:
            raise self.failure

    @staticmethod
    def stored(document):
        return BSON.encode(document).decode(CodecOptions(tz_aware=True))

    def insert_one(self, document):
        self.check()
        oid = ObjectId()
        self.documents[oid] = self.stored({**document, "_id": oid})
        return SimpleNamespace(inserted_id=oid)

    def find_one(self, query):
        self.check()
        return deepcopy(self.documents.get(query["_id"]))

    def find(self):
        self.check()
        documents = list(deepcopy(self.documents).values())
        return SimpleNamespace(sort=lambda _: sorted(documents, key=lambda d: (d["created_at"], d["_id"])))

    def find_one_and_update(self, query, update, *, return_document):
        self.check()
        if query["_id"] not in self.documents:
            return None
        self.documents[query["_id"]].update(self.stored(update["$set"]))
        return deepcopy(self.documents[query["_id"]])

    def delete_one(self, query):
        self.check()
        return SimpleNamespace(deleted_count=int(self.documents.pop(query["_id"], None) is not None))


class DisposableDatabase:
    def __init__(self):
        self.collection = DisposableCollection()
        self.options = None
        self.exists = False
        self.setup_failure = None

    def __getitem__(self, name):
        assert name == "rentals"
        return self.collection

    def create_collection(self, name, **options):
        if self.setup_failure:
            raise self.setup_failure
        if self.exists:
            raise CollectionInvalid("already exists")
        self.exists = True
        self.options = deepcopy(options)
        return self.collection

    def command(self, command, name, **options):
        assert command == "collMod" and name == "rentals"
        self.options = deepcopy(options)
        return {"ok": 1}


class Clock:
    now = datetime(2026, 10, 20, 7, 0, 0, 123456, tzinfo=timezone.utc)
    def __call__(self):
        return self.now


@pytest.fixture
def rig():
    database, clock = DisposableDatabase(), Clock()
    service = DocumentService(database, clock=clock)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(create_router(service, current_user_dependency=lambda: SimpleNamespace(id=6102)))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(client=client, database=database, clock=clock, service=service, app=app)


@pytest.fixture
def payload():
    return {"listingTitle": "  B disposable apartment  ", "propertyType": "apartment",
            "availableFrom": "2026-11-01T09:30:00-07:00"}


URL = "/api/doc-rentals"


def test_happy_crud_defaults_utc_and_full_put(rig, payload):
    assert rig.service.database is rig.database
    assert not rig.database.exists  # construction neither connects nor creates collections
    assert rig.client.get(URL).json() == []
    response = rig.client.post(URL, json={**payload, "description": "Initial", "status": "reserved"})
    assert response.status_code == 201
    created = response.json()
    assert ObjectId.is_valid(created["id"])
    assert created["listingTitle"] == "B disposable apartment"
    assert created["availableFrom"] == "2026-11-01T16:30:00Z"
    assert created["created_at"] == created["updated_at"] == "2026-10-20T07:00:00.123000Z"
    target = f'{URL}/{created["id"]}'
    assert rig.client.get(target).json() == created
    assert rig.client.get(URL).json() == [created]
    rig.clock.now += timedelta(minutes=2)
    replacement = {**payload, "listingTitle": "Replaced", "propertyType": "condo"}
    response = rig.client.put(target, json=replacement)
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] == "2026-10-20T07:02:00.123000Z"
    assert updated["description"] is None and updated["status"] == "available"
    assert updated["propertyType"] == "condo" and updated["listingTitle"] == "Replaced"
    assert rig.client.get(target).json() == updated
    response = rig.client.delete(target)
    assert response.status_code == 204 and response.content == b""
    assert rig.client.get(target).status_code == 404
    assert rig.client.get(URL).json() == []


def test_defaults_and_millisecond_roundtrip(rig, payload):
    response = rig.client.post(URL, json={**payload, "availableFrom": "2026-11-01T00:00:00.123456Z"})
    created = response.json()
    assert created["status"] == "available" and created["description"] is None
    assert created["availableFrom"] == "2026-11-01T00:00:00.123000Z"
    assert rig.client.get(f'{URL}/{created["id"]}').json() == created
    stored = rig.database.collection.documents[ObjectId(created["id"])]
    assert isinstance(stored["_id"], ObjectId)
    assert stored["availableFrom"].utcoffset() == timedelta(0)
    assert stored["created_at"].microsecond == 123000


INVALID = [
    ("listingTitle", None), ("listingTitle", ""), ("listingTitle", " \t\n"),
    ("listingTitle", "x" * 101), ("listingTitle", 123), ("listingTitle", ["title"]),
    ("description", 123), ("description", "x" * 5001),
    ("status", "pending"), ("status", None), ("status", 1),
    ("propertyType", "castle"), ("propertyType", None), ("propertyType", ["house"]),
    ("availableFrom", None), ("availableFrom", "bad-date"),
    ("availableFrom", "2026-02-30T12:00:00Z"),
    ("availableFrom", "2026-11-01"), ("availableFrom", "2026-11-01T09:30:00"),
    ("availableFrom", 1793520000), ("availableFrom", True), ("availableFrom", {}),
    ("created_at", "2000-01-01T00:00:00Z"), ("updated_at", "2000-01-01T00:00:00Z"),
    ("id", "507f1f77bcf86cd799439011"), ("_id", "507f1f77bcf86cd799439011"),
]


@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("field,value", INVALID)
def test_invalid_input_does_not_write(rig, payload, method, field, value):
    if method == "PUT":
        before = rig.client.post(URL, json=payload).json()
        target = f'{URL}/{before["id"]}'
    else:
        before, target = None, URL
    response = rig.client.request(method, target, json={**payload, field: value})
    assert response.status_code == 422
    assert response.json()["detail"]
    if before:
        assert rig.client.get(target).json() == before
    else:
        assert not rig.database.collection.documents


@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("field", ["listingTitle", "propertyType", "availableFrom"])
def test_required_fields(rig, payload, method, field):
    target = URL if method == "POST" else f'{URL}/{ObjectId()}'
    payload.pop(field)
    response = rig.client.request(method, target, json=payload)
    assert response.status_code == 422
    assert field in str(response.json()["detail"])


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
@pytest.mark.parametrize("identifier", ["bad", "0" * 23, "z" * 24])
def test_malformed_ids(rig, payload, method, identifier):
    response = rig.client.request(method, f"{URL}/{identifier}", json=payload if method == "PUT" else None)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_document_id"
    assert not rig.database.exists


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_missing_records(rig, payload, method):
    response = rig.client.request(method, f"{URL}/{ObjectId()}", json=payload if method == "PUT" else None)
    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"


def test_title_limit_is_after_trimming_and_unicode_is_text(rig, payload):
    assert rig.client.post(URL, json={**payload, "listingTitle": " " + "é" * 100 + " "}).status_code == 201


@pytest.mark.parametrize("stage", ["setup", "crud"])
@pytest.mark.parametrize("method", ["POST", "GET", "PUT", "DELETE"])
def test_unavailable_storage_is_sanitized(rig, payload, stage, method, caplog):
    error = ServerSelectionTimeoutError("PRIVATE_CONNECTION_SECRET")
    if stage == "setup":
        rig.database.setup_failure = error
    else:
        rig.service.prepare_collection()
        rig.database.collection.failure = error
    target = URL if method in {"POST", "GET"} else f'{URL}/{ObjectId()}'
    response = rig.client.request(method, target, json=payload if method in {"POST", "PUT"} else None)
    assert response.status_code == 503
    assert response.json()["code"] == "storage_unavailable"
    assert "PRIVATE_CONNECTION_SECRET" not in response.text + caplog.text
    assert "storage_unavailable" in caplog.text


def test_storage_validation_error_and_unexpected_failure(rig, payload, caplog):
    rig.service.prepare_collection()
    rig.database.collection.failure = OperationFailure("PRIVATE_FAILURE", code=121)
    response = rig.client.post(URL, json=payload)
    assert response.status_code == 422 and response.json()["code"] == "document_validation_failed"
    rig.database.collection.failure = RuntimeError("PRIVATE_FAILURE")
    response = rig.client.post(URL, json=payload)
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    assert "PRIVATE_FAILURE" not in response.text + caplog.text


@pytest.mark.parametrize("existing", [False, True])
def test_collection_validator_installed_without_removing_documents(rig, existing):
    rig.database.exists = existing
    oid = ObjectId()
    rig.database.collection.documents[oid] = {"fixture": "untouched"}
    rig.service.prepare_collection()
    options = rig.database.options
    assert options["validationLevel"] == "strict" and options["validationAction"] == "error"
    schema = options["validator"]["$jsonSchema"]
    assert set(schema["required"]) == {"listingTitle", "propertyType", "status", "availableFrom", "created_at", "updated_at"}
    assert schema["properties"]["listingTitle"]["maxLength"] == 100
    assert schema["properties"]["availableFrom"]["bsonType"] == "date"
    assert schema["properties"]["_id"]["bsonType"] == "objectId"
    assert rig.database.collection.documents[oid] == {"fixture": "untouched"}


def test_all_routes_require_authentication(payload):
    def denied():
        raise HTTPException(401, "Authentication required.")
    app = FastAPI()
    service = DocumentService(DisposableDatabase())
    app.include_router(create_router(service, current_user_dependency=denied))
    with TestClient(app) as client:
        for method, target in [("POST", URL), ("GET", URL), ("GET", f"{URL}/{ObjectId()}"),
                               ("PUT", f"{URL}/{ObjectId()}"), ("DELETE", f"{URL}/{ObjectId()}")]:
            assert client.request(method, target, json=payload).status_code == 401
    assert not service.database.exists


def test_invalid_json_is_rejected_before_storage(rig):
    response = rig.client.post(URL, content='{"listingTitle":', headers={"Content-Type": "application/json"})
    assert response.status_code == 422 and not rig.database.exists
