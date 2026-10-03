"""Offline contract checks; fake readers never substitute for live MySQL evidence."""

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.dialects import mysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rental_tools.contracts import SearchRentalsInput
from src.rental_tools.reader import MySQLRentalReader, RentalReaderConfigurationError
from src.rental_tools.registry import TOOL_REGISTRY
from src.rental_tools.service import RentalService


class FixtureReader:
    """Finite test fixtures model lower-case matching, not all MySQL Unicode rules."""

    def __init__(self):
        self.calls = []
        self.rows = [
            {"id": 9, "listing_title": "Straße Garden", "property_address": "École Road",
             "description": "A quiet apartment near the garden.", "property_type": "apartment",
             "manager_id": 1, "submitter_email": "private@example.com"},
            {"id": 2, "listing_title": "100% _Literal! \\ ' House", "property_address": "10 Main Street",
             "description": "A bright house beside the main street.", "property_type": "house",
             "manager_id": 1, "submitter_email": "private@example.com"},
            {"id": 4, "listing_title": "Main Condo", "property_address": "20 Main Street",
             "description": "An accessible condo with natural light.", "property_type": "condo",
             "manager_id": None, "password_hash": "must-not-appear"},
        ]

    def search_rentals(self, query, limit):
        self.calls.append(("search", query, limit))
        return [row for row in sorted(self.rows, key=lambda row: row["id"])
                if query.lower() in row["listing_title"].lower()
                or query.lower() in row["property_address"].lower()][:limit]

    def get_rental(self, rental_id):
        self.calls.append(("get", rental_id))
        return next((row for row in self.rows if row["id"] == rental_id), None)

    def count_rentals(self, manager_id):
        self.calls.append(("count", manager_id))
        if manager_id not in {1, 3}:
            return None
        return {"manager_id": manager_id, "manager_name": "Manager One" if manager_id == 1 else "Empty Manager",
                "count": sum(row["manager_id"] == manager_id for row in self.rows),
                "manager_email": "private-manager@example.com"}


@pytest.fixture
def reader():
    return FixtureReader()


@pytest.fixture
def service(reader):
    return RentalService(reader)


def test_search_projection_order_trim_default_and_limit(service, reader):
    result = service.search_rentals(query="  MAIN  ")
    assert result == {"ok": True, "error": None, "data": {
        "items": [
            {"id": 2, "listingTitle": "100% _Literal! \\ ' House", "propertyAddress": "10 Main Street", "propertyType": "house", "managerId": 1},
            {"id": 4, "listingTitle": "Main Condo", "propertyAddress": "20 Main Street", "propertyType": "condo", "managerId": None},
        ], "returnedCount": 2, "limit": 5}}
    assert reader.calls == [("search", "MAIN", 5)]
    assert service.search_rentals(query="main", limit=1)["data"]["returnedCount"] == 1


@pytest.mark.parametrize("query", ["%", "_", "!", "\\", "'", "100% _Literal!"])
def test_literal_search_characters(service, query):
    assert [row["id"] for row in service.search_rentals(query=query)["data"]["items"]] == [2]


def test_empty_search_succeeds_and_fixture_lower_is_not_casefold(service):
    assert service.search_rentals(query="not present")["data"]["items"] == []
    assert service.search_rentals(query="STRASSE")["data"]["items"] == []
    assert service.search_rentals(query="STRAßE")["data"]["items"][0]["id"] == 9
    assert service.search_rentals(query="ÉCOLE")["data"]["items"][0]["id"] == 9
    assert service.search_rentals(query="ecole")["data"]["items"] == []


@pytest.mark.parametrize("inputs", [
    {}, {"query": ""}, {"query": "   "}, {"query": "\t\n"}, {"query": "x" * 256},
    {"query": " " * 255 + "x"}, {"query": 1}, {"query": None},
    {"query": "x", "limit": True}, {"query": "x", "limit": 1.0},
    {"query": "x", "limit": "1"}, {"query": "x", "limit": 0},
    {"query": "x", "limit": 26}, {"query": "x", "unexpected": "value"},
])
def test_search_invalid_inputs_never_read(service, reader, inputs):
    result = service.search_rentals(**inputs)
    assert result["ok"] is False and result["data"] is None and result["error"]
    assert reader.calls == []


def test_search_boundary_inputs(service, reader):
    assert service.search_rentals(query="x" * 255, limit=25)["ok"] is True
    assert service.search_rentals(query=" " * 254 + "x", limit=1)["ok"] is True
    assert reader.calls[-1] == ("search", "x", 1)


def test_detail_projection_and_missing(service):
    assert service.get_rental(rental_id=9) == {"ok": True, "error": None, "data": {
        "id": 9, "listingTitle": "Straße Garden", "propertyAddress": "École Road",
        "description": "A quiet apartment near the garden.", "propertyType": "apartment", "managerId": 1}}
    assert service.get_rental(rental_id=10) == {"ok": False, "data": None, "error": "Rental 10 was not found."}


def test_manager_count_existing_empty_and_missing(service):
    assert service.count_rentals(manager_id=1) == {"ok": True, "error": None, "data": {
        "managerId": 1, "managerName": "Manager One", "count": 2}}
    assert service.count_rentals(manager_id=3)["data"]["count"] == 0
    assert service.count_rentals(manager_id=10) == {"ok": False, "data": None, "error": "Property manager 10 was not found."}


@pytest.mark.parametrize("name,key", [("get_rental", "rental_id"), ("count_rentals", "manager_id")])
@pytest.mark.parametrize("value", [0, -1, True, 1.0, "1", None])
def test_id_types_and_ranges(service, reader, name, key, value):
    assert getattr(service, name)(**{key: value})["ok"] is False
    assert reader.calls == []


@pytest.mark.parametrize("name,inputs", [("get_rental", {}), ("count_rentals", {}),
    ("get_rental", {"rental_id": 1, "include_contact": True}),
    ("count_rentals", {"manager_id": 1, "sql": "SELECT password_hash FROM users"})])
def test_core_rejects_missing_and_extra_arguments(service, reader, name, inputs):
    assert getattr(service, name)(**inputs)["ok"] is False
    assert reader.calls == []


def test_dependency_errors_are_sanitized():
    class BrokenReader(FixtureReader):
        def get_rental(self, rental_id):
            raise RuntimeError("mysql+pymysql://secret:password@host/s6102_rel private@example.com")
    assert RentalService(BrokenReader()).get_rental(rental_id=1) == {
        "ok": False, "data": None, "error": "Rental data is temporarily unavailable."}


def test_registry_and_schemas_are_shared():
    assert set(TOOL_REGISTRY) == {"search_rentals", "get_rental", "count_rentals"}
    assert TOOL_REGISTRY["search_rentals"].input_model is SearchRentalsInput
    for spec in TOOL_REGISTRY.values():
        assert spec.input_model.model_json_schema()["additionalProperties"] is False
    schema = SearchRentalsInput.model_json_schema()
    assert schema["required"] == ["query"]
    assert schema["properties"]["query"]["maxLength"] == 255
    assert schema["properties"]["limit"]["maximum"] == 25


class FakeResult:
    def __init__(self, rows):
        self.rows = rows
    def mappings(self):
        return self
    def all(self):
        return list(self.rows)
    def first(self):
        return self.rows[0] if self.rows else None


class RecordingEngine:
    def __init__(self, rows=()):
        self.rows = rows
        self.statements = []
    def connect(self):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, statement):
        self.statements.append(statement.compile(dialect=mysql.dialect()))
        return FakeResult(self.rows)
    def dispose(self):
        pass


def test_mysql_adapter_is_lazy_and_selects_explicit_safe_fields(monkeypatch):
    import src.rental_tools.reader as adapter
    engine = RecordingEngine()
    calls = []
    monkeypatch.setattr(adapter, "create_engine", lambda *args, **kwargs: calls.append((args, kwargs)) or engine)
    db = MySQLRentalReader("mysql+pymysql://local:unused@127.0.0.1:3308/s6102_rel")
    assert calls == []
    assert db.search_rentals("A!%_\\'B", 5) == []
    assert db.get_rental(3) is None
    assert db.count_rentals(5) is None
    assert len(calls) == 1
    sql = [str(stmt) for stmt in engine.statements]
    assert all(statement.lstrip().startswith("SELECT ") for statement in sql)
    assert all("submitter_email" not in statement and "SELECT *" not in statement for statement in sql)
    assert "utf8mb4_bin" in sql[0] and "lower(" in sql[0].lower()
    assert "ORDER BY rentals.id ASC" in sql[0]
    assert "ESCAPE '!'" in sql[0] and "A!%_" not in sql[0]
    assert "%A!!!%!_\\'B%" in engine.statements[0].params.values()
    assert "LEFT OUTER JOIN" in sql[2] and "count(rentals.id)" in sql[2]


@pytest.mark.parametrize("url", [None, "", "garbage", "sqlite:///s6102_rel", "mysql+pymysql://host/other", "postgresql://host/s6102_rel"])
def test_mysql_adapter_requires_explicit_scoped_dsn(monkeypatch, url):
    monkeypatch.delenv("HW5_MCP_DATABASE_URL", raising=False)
    reader = MySQLRentalReader(url)
    with pytest.raises(RentalReaderConfigurationError, match="HW5_MCP_DATABASE_URL"):
        reader.get_rental(1)


def test_imports_do_not_create_engines_or_write_stdout():
    code = """
import socket
import sqlalchemy
def forbidden(*args, **kwargs):
    raise AssertionError("Module import attempted database or network access")
sqlalchemy.create_engine = forbidden
socket.socket.connect = forbidden
import src.rental_tools.reader
import src.rental_tools.service
import src.rental_tools.registry
import src.mcp_servers.rentals
src.mcp_servers.rentals.create_server()
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
