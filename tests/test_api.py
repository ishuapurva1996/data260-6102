"""Part 2 rental API behavior, with a fresh in-memory app for every test."""

import importlib.util
from pathlib import Path

import pytest


APP_PATH = Path(__file__).resolve().parents[1] / "code/web_application/main.py"
spec = importlib.util.spec_from_file_location("rental_web_app", APP_PATH)
web_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_app)

from fastapi.testclient import TestClient


@pytest.fixture
def payload():
    return {
        "listingTitle": "Bright Studio",
        "propertyAddress": "700 Market Street, San Jose, CA",
        "submitterEmail": "owner@example.com",
        "description": "A quiet studio with natural light and nearby transit.",
        "propertyType": "apartment",
        "termsAccepted": True,
    }


@pytest.fixture
def client():
    with TestClient(web_app.create_app()) as client:
        yield client


def test_seed_collection_is_valid_and_not_cached(client):
    response = client.get("/api/rentals")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    rentals = response.json()
    assert [rental["id"] for rental in rentals] == [1, 2]
    for rental in rentals:
        assert type(rental["id"]) is int
        assert set(rental) == {
            "id", "listingTitle", "propertyAddress", "submitterEmail",
            "description", "propertyType", "termsAccepted",
        }
        assert rental["termsAccepted"] is True
        assert len(rental["description"].strip()) >= 26


def test_home_and_assets_work_from_another_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    isolated_spec = importlib.util.spec_from_file_location("rental_other_cwd", APP_PATH)
    isolated_module = importlib.util.module_from_spec(isolated_spec)
    isolated_spec.loader.exec_module(isolated_module)
    with TestClient(isolated_module.create_app()) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "text/html" in home.headers["content-type"]
        assert "/static/styles.css" in home.text
        assert "/static/app.js" in home.text
        for asset, content_type in (("styles.css", "text/css"), ("app.js", "javascript")):
            response = client.get(f"/static/{asset}")
            assert response.status_code == 200
            assert content_type in response.headers["content-type"]


def test_create_assigns_id_and_survives_home_reload(client, payload):
    response = client.post("/api/rentals", json=payload)
    assert response.status_code == 201
    assert response.json() == {"id": 3, **payload}
    assert client.get("/").status_code == 200
    assert client.get("/api/rentals").json()[-1] == response.json()


def test_create_trims_text_and_accepts_26_character_description(client, payload):
    payload.update(
        listingTitle="  Café près du parc  ",
        propertyAddress="  123 José Street  ",
        description="  " + "x" * 26 + "  ",
    )
    response = client.post("/api/rentals", json=payload)
    assert response.status_code == 201
    assert response.json()["listingTitle"] == "Café près du parc"
    assert response.json()["propertyAddress"] == "123 José Street"
    assert response.json()["description"] == "x" * 26


@pytest.mark.parametrize("field,value", [
    ("listingTitle", " \t\n "),
    ("propertyAddress", " \t "),
    ("submitterEmail", "not-an-email"),
    ("description", " " + "x" * 25 + " "),
    ("propertyType", "castle"),
    ("termsAccepted", False),
    ("termsAccepted", 1),
    ("termsAccepted", "true"),
])
def test_invalid_create_does_not_mutate_store(client, payload, field, value):
    before = client.get("/api/rentals").json()
    payload[field] = value
    response = client.post("/api/rentals", json=payload)
    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])
    assert client.get("/api/rentals").json() == before


def test_create_rejects_client_assigned_id(client, payload):
    response = client.post("/api/rentals", json={**payload, "id": 9000})
    assert response.status_code == 422
    assert client.post("/api/rentals", json=payload).json()["id"] == 3


def test_malformed_json_returns_validation_error_without_mutation(client):
    before = client.get("/api/rentals").json()
    response = client.post(
        "/api/rentals", content='{"listingTitle":', headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.get("/api/rentals").json() == before


def test_create_uses_current_maximum_and_starts_at_one_when_empty(payload):
    seeds = [{**payload, "id": rental_id} for rental_id in [7, 1, 3]]
    with TestClient(web_app.create_app(seeds)) as client:
        assert client.post("/api/rentals", json=payload).json()["id"] == 8
    with TestClient(web_app.create_app([])) as client:
        assert client.post("/api/rentals", json=payload).json()["id"] == 1


def test_update_id_one_changes_only_title_and_address(client):
    before = client.get("/api/rentals").json()
    response = client.put("/api/rentals/1", json={
        "listingTitle": "  Updated downtown rental  ",
        "propertyAddress": "  42 New Street  ",
    })
    expected = {
        **before[0], "listingTitle": "Updated downtown rental", "propertyAddress": "42 New Street",
    }
    assert response.status_code == 200
    assert response.json() == expected
    assert client.get("/api/rentals").json() == [expected, before[1]]


@pytest.mark.parametrize("changes", [
    {"listingTitle": " ", "propertyAddress": "42 New Street"},
    {"listingTitle": "New title", "propertyAddress": "\t"},
    {"listingTitle": "New title"},
    {"listingTitle": "New title", "propertyAddress": "42 New Street", "termsAccepted": False},
])
def test_invalid_update_keeps_existing_record(client, changes):
    before = client.get("/api/rentals").json()
    assert client.put("/api/rentals/1", json=changes).status_code == 422
    assert client.get("/api/rentals").json() == before


def test_unknown_update_returns_404_without_mutation(client):
    before = client.get("/api/rentals").json()
    response = client.put("/api/rentals/999", json={
        "listingTitle": "Unknown rental", "propertyAddress": "42 New Street",
    })
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)
    assert client.get("/api/rentals").json() == before


def test_highest_deletion_uses_global_max_not_order_or_search(payload):
    seeds = [{**payload, "id": rental_id, "listingTitle": f"Rental {rental_id}"}
             for rental_id in [7, 1, 3]]
    with TestClient(web_app.create_app(seeds)) as client:
        assert [r["id"] for r in client.get("/api/rentals?q=Rental%201").json()] == [1]
        response = client.delete("/api/rentals/highest")
        assert response.status_code == 204
        assert response.content == b""
        assert [r["id"] for r in client.get("/api/rentals").json()] == [1, 3]


def test_chosen_deletion_removes_only_requested_id(payload):
    seeds = [{**payload, "id": rental_id} for rental_id in [1, 3, 7]]
    with TestClient(web_app.create_app(seeds)) as client:
        response = client.delete("/api/rentals/3")
        assert response.status_code == 204
        assert response.content == b""
        assert [r["id"] for r in client.get("/api/rentals").json()] == [1, 7]


def test_missing_delete_returns_404_without_mutation(client):
    before = client.get("/api/rentals").json()
    assert client.delete("/api/rentals/999").status_code == 404
    assert client.get("/api/rentals").json() == before


def test_empty_store_highest_delete_is_404_not_path_validation_error():
    with TestClient(web_app.create_app([])) as client:
        assert client.get("/api/rentals").json() == []
        response = client.delete("/api/rentals/highest")
        assert response.status_code == 404
        assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("query", [None, "", " \t\n "])
def test_blank_search_returns_all_records(client, query):
    expected = client.get("/api/rentals").json()
    params = {} if query is None else {"q": query}
    response = client.get("/api/rentals", params=params)
    assert response.status_code == 200
    assert response.json() == expected


@pytest.mark.parametrize("query,expected_ids", [
    ("  strasse  ", [5]),
    ("mArKeT", [2]),
    ("garden", [5, 2]),
    ("no-such-rental", []),
    ("owner@example.com", []),
])
def test_search_matches_title_or_address_case_insensitively(payload, query, expected_ids):
    seeds = [
        {**payload, "id": 5, "listingTitle": "Straße Garden Flat", "propertyAddress": "10 Oak Road"},
        {**payload, "id": 2, "listingTitle": "City Studio", "propertyAddress": "20 Garden Market Road"},
    ]
    with TestClient(web_app.create_app(seeds)) as client:
        response = client.get("/api/rentals", params={"q": query})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert [rental["id"] for rental in response.json()] == expected_ids
        assert len(client.get("/api/rentals").json()) == 2


def test_openapi_separates_client_fields_from_server_id(client):
    schema = client.get("/openapi.json").json()
    models = schema["components"]["schemas"]
    assert "id" not in models["RentalCreate"]["properties"]
    assert set(models["RentalUpdate"]["properties"]) == {"listingTitle", "propertyAddress"}
    assert models["Rental"]["properties"]["id"]["type"] == "integer"
    assert "201" in schema["paths"]["/api/rentals"]["post"]["responses"]
    assert "204" in schema["paths"]["/api/rentals/highest"]["delete"]["responses"]
