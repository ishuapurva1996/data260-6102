"""Current rental API contract against real MySQL (supersedes HW3 memory tests)."""
import pytest
from sqlalchemy import delete

from web_application.models import Rental


def create(client, payload):
    response = client.post("/api/rentals", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def missing_id(client):
    return max((row["id"] for row in client.get("/api/rentals").json()), default=0) + 1


def test_create_list_read_and_database_assigned_id(hw4_logged_in, rental_payload):
    client = hw4_logged_in
    row = create(client, rental_payload)
    assert isinstance(row["id"], int) and row["id"] > 0
    assert row == {**rental_payload, "id": row["id"]}
    assert client.get(f'/api/rentals/{row["id"]}').json() == row
    response = client.get("/api/rentals")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert row in response.json()
    ids = [item["id"] for item in response.json()]
    assert ids == sorted(ids)


@pytest.mark.parametrize("changes", [
    {"listingTitle": " "}, {"listingTitle": "x" * 256},
    {"propertyAddress": "\t"}, {"propertyAddress": "x" * 256},
    {"submitterEmail": "not-an-email"}, {"description": "x" * 25},
    {"propertyType": "castle"}, {"termsAccepted": False},
    {"termsAccepted": "true"}, {"termsAccepted": 1},
    {"id": 9000}, {"unexpected": "value"},
])
def test_invalid_create_returns_422_without_a_rental_write(hw4_logged_in, rental_payload, changes):
    client = hw4_logged_in
    before = client.get("/api/rentals").json()
    response = client.post("/api/rentals", json={**rental_payload, **changes})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.get("/api/rentals").json() == before


@pytest.mark.parametrize("field", ["listingTitle", "propertyAddress", "submitterEmail", "description",
                                   "propertyType", "termsAccepted"])
def test_create_requires_all_six_fields(hw4_logged_in, rental_payload, field):
    before = hw4_logged_in.get("/api/rentals").json()
    del rental_payload[field]
    assert hw4_logged_in.post("/api/rentals", json=rental_payload).status_code == 422
    assert hw4_logged_in.get("/api/rentals").json() == before


def test_malformed_json_does_not_write(hw4_logged_in):
    before = hw4_logged_in.get("/api/rentals").json()
    response = hw4_logged_in.post("/api/rentals", content='{"listingTitle":',
                                 headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert hw4_logged_in.get("/api/rentals").json() == before


def test_two_field_update_trims_text_and_preserves_other_values(hw4_logged_in, rental_payload):
    row = create(hw4_logged_in, rental_payload)
    response = hw4_logged_in.put(f'/api/rentals/{row["id"]}', json={
        "listingTitle": "  Updated downtown rental  ", "propertyAddress": "  42 New Street  "})
    expected = {**row, "listingTitle": "Updated downtown rental", "propertyAddress": "42 New Street"}
    assert response.status_code == 200
    assert response.json() == expected
    assert hw4_logged_in.get(f'/api/rentals/{row["id"]}').json() == expected


@pytest.mark.parametrize("changes", [
    {"listingTitle": " ", "propertyAddress": "42 New Street"},
    {"listingTitle": "New title", "propertyAddress": "\t"},
    {"listingTitle": "New title"}, {"propertyAddress": "42 New Street"},
    {"listingTitle": "New title", "propertyAddress": "42 New Street", "termsAccepted": False},
    {"listingTitle": "New title", "propertyAddress": "42 New Street", "id": 1},
])
def test_invalid_update_preserves_record(hw4_logged_in, rental_payload, changes):
    row = create(hw4_logged_in, rental_payload)
    assert hw4_logged_in.put(f'/api/rentals/{row["id"]}', json=changes).status_code == 422
    assert hw4_logged_in.get(f'/api/rentals/{row["id"]}').json() == row


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_missing_record_returns_json_404(hw4_logged_in, method):
    before = hw4_logged_in.get("/api/rentals").json()
    kwargs = {"json": {"listingTitle": "Unknown rental", "propertyAddress": "42 New Street"}} if method == "put" else {}
    response = hw4_logged_in.request(method, f"/api/rentals/{missing_id(hw4_logged_in)}", **kwargs)
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)
    assert hw4_logged_in.get("/api/rentals").json() == before


@pytest.mark.parametrize("rental_id", [0, -1, "not-an-id"])
def test_invalid_record_ids_return_422(hw4_logged_in, rental_id):
    assert hw4_logged_in.get(f"/api/rentals/{rental_id}").status_code == 422


def test_delete_selected_record_and_do_not_reuse_its_id(hw4_logged_in, rental_payload):
    first = create(hw4_logged_in, rental_payload)
    second = create(hw4_logged_in, rental_payload)
    response = hw4_logged_in.delete(f'/api/rentals/{second["id"]}')
    assert response.status_code == 204 and response.content == b""
    assert hw4_logged_in.get(f'/api/rentals/{second["id"]}').status_code == 404
    assert hw4_logged_in.get(f'/api/rentals/{first["id"]}').json() == first
    third = create(hw4_logged_in, rental_payload)
    assert third["id"] > second["id"]


def test_highest_deletion_uses_global_max_and_returns_empty_204(hw4_logged_in, rental_payload):
    create(hw4_logged_in, rental_payload)
    create(hw4_logged_in, rental_payload)
    before = hw4_logged_in.get("/api/rentals").json()
    highest = max(row["id"] for row in before)
    # Any changed row, including a pre-existing row, is restored by outer rollback.
    assert hw4_logged_in.get("/api/rentals", params={"q": "no-such-title-6102"}).json() == []
    response = hw4_logged_in.delete("/api/rentals/highest")
    assert response.status_code == 204 and response.content == b""
    assert hw4_logged_in.get("/api/rentals").json() == [row for row in before if row["id"] != highest]


def test_highest_on_empty_table_is_404_not_dynamic_path_422(hw4_logged_in, hw4_session_factory):
    # This deletion lives only inside this test's outer transaction and is undone.
    with hw4_session_factory() as db:
        db.execute(delete(Rental))
        db.commit()
    response = hw4_logged_in.delete("/api/rentals/highest")
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("query", [None, "", " \t\n "])
def test_blank_search_returns_every_record(hw4_logged_in, query):
    expected = hw4_logged_in.get("/api/rentals").json()
    params = {} if query is None else {"q": query}
    assert hw4_logged_in.get("/api/rentals", params=params).json() == expected


def test_search_matches_title_or_address_case_insensitively_in_id_order(hw4_logged_in, rental_payload):
    marker = rental_payload["listingTitle"]
    first = create(hw4_logged_in, {**rental_payload, "listingTitle": f"{marker} Garden"})
    second = create(hw4_logged_in, {**rental_payload, "listingTitle": "City studio",
                                    "propertyAddress": f"{marker} Market Road"})
    result = hw4_logged_in.get("/api/rentals", params={"q": f"  {marker.upper()}  "})
    assert result.status_code == 200
    assert result.json() == [first, second]
    email_matches = hw4_logged_in.get("/api/rentals", params={"q": "owner@example.com"}).json()
    assert not ({first["id"], second["id"]} & {row["id"] for row in email_matches})


def test_search_treats_sql_wildcards_as_literal_text(hw4_logged_in, rental_payload):
    marker = rental_payload["listingTitle"]
    literal = create(hw4_logged_in, {**rental_payload, "listingTitle": f"{marker}%_"})
    create(hw4_logged_in, {**rental_payload, "listingTitle": f"{marker}XX"})
    assert hw4_logged_in.get("/api/rentals", params={"q": f"{marker}%_"}).json() == [literal]


def test_openapi_separates_create_update_and_response_fields(hw4_logged_in):
    schema = hw4_logged_in.get("/openapi.json").json()
    models = schema["components"]["schemas"]
    assert "id" not in models["RentalCreate"]["properties"]
    assert set(models["RentalUpdate"]["properties"]) == {"listingTitle", "propertyAddress"}
    assert models["RentalResponse"]["properties"]["id"]["type"] == "integer"
    assert "201" in schema["paths"]["/api/rentals"]["post"]["responses"]
    assert "204" in schema["paths"]["/api/rentals/highest"]["delete"]["responses"]
