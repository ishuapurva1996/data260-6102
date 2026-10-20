"""Additional public schema, stored-title and capture cleanup checks; all offline."""
from datetime import datetime, timezone
import re

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from scripts.hw06.part1.verify import CheckFailed, run_api_checks
from src.hw06_documents.schemas import RentalCreate, RentalUpdate
from src.hw06_documents.validation import RENTAL_VALIDATOR
from src.hw06_shared.database import MongoConnection
from src.hw06_shared.config import HW6Config
from src.hw06_documents.service import DocumentService
from src.hw06_shared.errors import install_error_handlers
from web_application.routers.auth import require_user
from web_application.routers.doc_rentals import create_router


@pytest.mark.parametrize("schema", [RentalCreate, RentalUpdate])
@pytest.mark.parametrize("status", ["available", "reserved", "rented"])
@pytest.mark.parametrize("property_type", ["apartment", "house", "condo", "townhouse"])
def test_all_categorical_options(schema, status, property_type):
    row = schema(listingTitle="Sample", propertyType=property_type, status=status,
                 availableFrom=datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert row.status == status and row.propertyType == property_type


@pytest.mark.parametrize("title", ["\u00a0", "\u2003", "\x1c", "\u3000", "\n", " title", "title\n"])
def test_stored_title_pattern_matches_trim_contract(title):
    # Python checks the portable regex; actual MongoDB enforcement needs the live capture.
    pattern = RENTAL_VALIDATOR["$jsonSchema"]["properties"]["listingTitle"]["pattern"]
    assert re.search(pattern, title) is None


@pytest.mark.parametrize("title", ["a", "Bright home", "é" * 100, "Two\nlines"])
def test_stored_title_pattern_accepts_trimmed_text(title):
    pattern = RENTAL_VALIDATOR["$jsonSchema"]["properties"]["listingTitle"]["pattern"]
    assert re.search(pattern, title) is not None


def test_real_default_auth_dependency_is_injectable_without_changing_routes():
    class NoStorage:
        def __getitem__(self, name):
            return object()
    service = DocumentService(NoStorage())
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(create_router(service))
    # Resolve the existing require_user key through FastAPI's normal override mechanism.
    app.dependency_overrides[require_user] = lambda: object()
    with TestClient(app) as client:
        response = client.get("/api/doc-rentals/bad-id")
    assert response.status_code == 422 and response.json()["code"] == "invalid_document_id"


def test_capture_cleans_own_fixture_even_when_a_later_check_fails():
    oid, unrelated = ObjectId(), ObjectId()
    documents = {unrelated: {"_id": unrelated, "description": "another run"}}

    class Collection:
        def find(self, query, projection):
            return [row for row in list(documents.values()) if row["description"] == query["description"]]
        def delete_one(self, query):
            documents.pop(query["_id"], None)

    class Database:
        def __getitem__(self, name):
            return Collection()

    class Client:
        def request(self, method, path, **kwargs):
            payload = kwargs["json"]
            documents[oid] = {"_id": oid, "description": payload["description"]}
            # Deliberately fail the first postcondition after a successful real-shaped POST.
            return type("Response", (), {"status_code": 201, "content": b"json",
                "json": lambda self: {"id": str(oid), "listingTitle": "wrong title"}})()

    result = {}
    with pytest.raises(CheckFailed, match="Title not trimmed"):
        run_api_checks(Client(), Database(), result)
    assert set(documents) == {unrelated}
    assert result["responses"][0]["status_code"] == 201
    assert result["cleanup"]["count"] == 1


def test_connection_retains_one_shared_database_for_service():
    database = type("Database", (), {"__getitem__": lambda self, name: object()})()
    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def __getitem__(self, name):
            return database
        def close(self):
            pass
    with MongoConnection(HW6Config(), client_factory=Client) as connection:
        assert DocumentService(connection.database).database is connection.database
