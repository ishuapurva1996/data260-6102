"""HW5 API contracts; database cases use the explicit real-MySQL fixtures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from web_application.main import create_app
from web_application.models import PropertyManager, Rental


def test_openapi_advertises_hw5_contract_without_connecting():
    schema = create_app().openapi()
    assert "/api/property-managers" in schema["paths"]
    assert "/api/property-managers/{manager_id}/rentals" in schema["paths"]
    models = schema["components"]["schemas"]
    assert {"listingCode", "availableUnits", "managerId", "createdAt", "updatedAt"} <= set(
        models["RentalResponse"]["properties"])
    assert set(models["ManagerCreate"]["required"]) == {"name", "company", "email"}


@pytest.fixture
def manager_payload():
    return {"name": "Orchard Manager", "company": "Orchard Homes",
            "email": f"manager-{uuid4().hex}@example.com"}


def create_manager(client, payload):
    response = client.post("/api/property-managers", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_rental(client, payload):
    response = client.post("/api/rentals", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def absent_id(factory, model):
    with factory() as db:
        return (db.scalar(select(func.max(model.id))) or 0) + 1


def test_manager_crud_normalizes_email_and_utc_timestamps(hw4_logged_in, manager_payload):
    client = hw4_logged_in
    original = create_manager(client, {**manager_payload, "name": "  Orchard Manager  ",
                                       "email": manager_payload["email"].upper()})
    assert original["name"] == manager_payload["name"]
    assert original["email"] == manager_payload["email"]
    assert datetime.fromisoformat(original["createdAt"].replace("Z", "+00:00")).tzinfo == timezone.utc
    assert original["createdAt"] == original["updatedAt"]
    assert client.get(f'/api/property-managers/{original["id"]}').json() == original
    response = client.put(f'/api/property-managers/{original["id"]}', json={
        **manager_payload, "name": "Updated Manager", "company": "New Company"})
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Updated Manager" and updated["company"] == "New Company"
    assert updated["createdAt"] == original["createdAt"]
    assert updated["updatedAt"] > original["updatedAt"]
    empty = client.get(f'/api/property-managers/{original["id"]}/rentals')
    assert empty.json() == [] and empty.headers["X-Total-Count"] == "0"
    deleted = client.delete(f'/api/property-managers/{original["id"]}')
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(f'/api/property-managers/{original["id"]}').status_code == 404


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"company": "\t"}, {"email": "invalid"}, {"email": None},
    {"email": "ß" * 130 + "@example.com"},
    {"name": "n" * 256}, {"company": "c" * 256}, {"id": 123},
])
def test_manager_rejects_invalid_fields(hw4_logged_in, manager_payload, changes):
    assert hw4_logged_in.post("/api/property-managers", json={**manager_payload, **changes}).status_code == 422


@pytest.mark.parametrize("field", ["name", "company", "email"])
def test_manager_create_and_update_require_meaningful_fields(hw4_logged_in, manager_payload, field):
    row = create_manager(hw4_logged_in, manager_payload)
    del manager_payload[field]
    assert hw4_logged_in.post("/api/property-managers", json=manager_payload).status_code == 422
    assert hw4_logged_in.put(f'/api/property-managers/{row["id"]}', json=manager_payload).status_code == 422


def test_real_unique_email_conflicts_rollback_and_next_request_works(hw4_logged_in, manager_payload):
    client = hw4_logged_in
    first = create_manager(client, manager_payload)
    assert client.post("/api/property-managers", json={
        **manager_payload, "email": manager_payload["email"].upper()}).status_code == 409
    second = create_manager(client, {**manager_payload, "email": f"other-{uuid4().hex}@example.com"})
    assert client.put(f'/api/property-managers/{second["id"]}', json=manager_payload).status_code == 409
    assert client.get(f'/api/property-managers/{first["id"]}').json() == first
    assert client.get(f'/api/property-managers/{second["id"]}').json() == second


def test_rental_defaults_relationship_restrict_and_full_update(hw4_logged_in, rental_payload, manager_payload):
    client = hw4_logged_in
    manager = create_manager(client, manager_payload)
    old = create_rental(client, rental_payload)
    assert old["listingCode"] == f'S6102-R-{old["id"]}'
    assert old["availableUnits"] == 1 and old["managerId"] is None
    assert old["createdAt"] == old["updatedAt"]
    response = client.put(f'/api/rentals/{old["id"]}', json={
        "listingTitle": "Updated Rental", "propertyAddress": "12 New Road",
        "listingCode": f"S6102-R-{uuid4().int}", "availableUnits": 0, "managerId": manager["id"]})
    assert response.status_code == 200
    row = response.json()
    assert row["availableUnits"] == 0 and row["managerId"] == manager["id"]
    assert row["submitterEmail"] == old["submitterEmail"] and row["description"] == old["description"]
    assert row["createdAt"] == old["createdAt"] and row["updatedAt"] > old["updatedAt"]
    relation = client.get(f'/api/property-managers/{manager["id"]}/rentals')
    assert relation.json() == [row] and relation.headers["X-Total-Count"] == "1"
    assert client.delete(f'/api/property-managers/{manager["id"]}').status_code == 409
    assert client.get(f'/api/rentals/{row["id"]}').json() == row
    assert client.delete(f'/api/rentals/{row["id"]}').status_code == 204
    assert client.delete(f'/api/property-managers/{manager["id"]}').status_code == 204


@pytest.mark.parametrize("changes", [
    {"listingCode": "invalid"}, {"listingCode": "S6102-R-0"}, {"listingCode": "S6102-R-01"},
    {"listingCode": "S6102-R--2"}, {"listingCode": "S6102-R-1.5"}, {"listingCode": None},
    {"availableUnits": -1}, {"availableUnits": 1.5}, {"availableUnits": True},
    {"availableUnits": None}, {"availableUnits": 2147483648},
    {"managerId": 0}, {"managerId": -1}, {"managerId": True}, {"managerId": "1"},
])
def test_rental_new_field_validation_for_create_and_update(hw4_logged_in, rental_payload, changes):
    row = create_rental(hw4_logged_in, rental_payload)
    assert hw4_logged_in.post("/api/rentals", json={**rental_payload, **changes}).status_code == 422
    assert hw4_logged_in.put(f'/api/rentals/{row["id"]}', json={
        "listingTitle": row["listingTitle"], "propertyAddress": row["propertyAddress"], **changes}).status_code == 422
    assert hw4_logged_in.get(f'/api/rentals/{row["id"]}').json() == row


def test_invalid_supplied_manager_and_unique_listing_conflicts_rollback(
    hw4_logged_in, hw4_session_factory, rental_payload,
):
    client = hw4_logged_in
    missing = absent_id(hw4_session_factory, PropertyManager)
    assert client.post("/api/rentals", json={**rental_payload, "managerId": missing}).status_code == 422
    code = f"S6102-R-{uuid4().int}"
    first = create_rental(client, {**rental_payload, "listingCode": code})
    assert client.post("/api/rentals", json={**rental_payload, "listingCode": code}).status_code == 409
    second = create_rental(client, rental_payload)
    update = {"listingTitle": second["listingTitle"], "propertyAddress": second["propertyAddress"]}
    assert client.put(f'/api/rentals/{second["id"]}', json={**update, "listingCode": code}).status_code == 409
    assert client.put(f'/api/rentals/{second["id"]}', json={**update, "managerId": missing}).status_code == 422
    assert client.get(f'/api/rentals/{first["id"]}').json() == first
    assert client.get(f'/api/rentals/{second["id"]}').json() == second


def test_pagination_totals_stable_order_filter_and_relationship(
    hw4_logged_in, rental_payload, manager_payload,
):
    client = hw4_logged_in
    manager = create_manager(client, manager_payload)
    rows = [create_rental(client, {**rental_payload, "managerId": manager["id"],
                                  "listingTitle": f'{rental_payload["listingTitle"]} {i}'}) for i in range(3)]
    for path, params in [('/api/rentals', {"q": rental_payload["listingTitle"]}),
                         (f'/api/property-managers/{manager["id"]}/rentals', {})]:
        response = client.get(path, params={**params, "limit": 2, "offset": 1})
        assert response.json() == rows[1:] and response.headers["X-Total-Count"] == "3"
        empty = client.get(path, params={**params, "limit": 2, "offset": 3})
        assert empty.json() == [] and empty.headers["X-Total-Count"] == "3"
    managers = client.get('/api/property-managers', params={"limit": 2})
    assert managers.status_code == 200 and len(managers.json()) <= 2
    assert int(managers.headers["X-Total-Count"]) >= 1
    assert [row["id"] for row in managers.json()] == sorted(row["id"] for row in managers.json())


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1},
                                    {"limit": "nan"}, {"offset": "1.1"}])
def test_invalid_pagination(hw4_logged_in, manager_payload, params):
    manager = create_manager(hw4_logged_in, manager_payload)
    for path in ('/api/rentals', '/api/property-managers',
                 f'/api/property-managers/{manager["id"]}/rentals'):
        assert hw4_logged_in.get(path, params=params).status_code == 422


def test_missing_manager_and_relationship_are_404(hw4_logged_in, hw4_session_factory, manager_payload):
    missing = absent_id(hw4_session_factory, PropertyManager)
    path = f"/api/property-managers/{missing}"
    assert hw4_logged_in.get(path).status_code == 404
    assert hw4_logged_in.get(path + "/rentals").status_code == 404
    assert hw4_logged_in.put(path, json=manager_payload).status_code == 404
    assert hw4_logged_in.delete(path).status_code == 404


def test_manager_endpoints_require_authentication(hw4_client, manager_payload):
    for method, path, payload in [('get', '/api/property-managers', None),
                                 ('post', '/api/property-managers', manager_payload),
                                 ('get', '/api/property-managers/1', None),
                                 ('put', '/api/property-managers/1', manager_payload),
                                 ('delete', '/api/property-managers/1', None),
                                 ('get', '/api/property-managers/1/rentals', None)]:
        response = hw4_client.request(method, path, **({"json": payload} if payload else {}))
        assert response.status_code == 401


def test_orm_delete_cannot_null_loaded_children(hw4_logged_in, hw4_session_factory, manager_payload, rental_payload):
    manager = create_manager(hw4_logged_in, manager_payload)
    rental = create_rental(hw4_logged_in, {**rental_payload, "managerId": manager["id"]})
    with hw4_session_factory() as db:
        row = db.get(PropertyManager, manager["id"])
        assert [child.id for child in row.rentals] == [rental["id"]]
        db.delete(row)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.get(Rental, rental["id"]).manager_id == manager["id"]


def test_concurrent_generated_codes_are_unique_and_complete(hw4_engine, rental_payload):
    from web_application.routers.rentals import create_rental as insert_rental
    from web_application.schemas import RentalCreate

    def insert(number):
        with hw4_engine.connect() as connection:
            outer = connection.begin()
            factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
            try:
                with factory() as db:
                    return insert_rental(RentalCreate(**{
                        **rental_payload, "listingTitle": f'{rental_payload["listingTitle"]} concurrent {number}'}), db)
            finally:
                outer.rollback()

    with ThreadPoolExecutor(max_workers=4) as executor:
        rows = list(executor.map(insert, range(4)))
    assert len({row["id"] for row in rows}) == 4
    assert len({row["listingCode"] for row in rows}) == 4
    assert all(row["listingCode"] == f'S6102-R-{row["id"]}' for row in rows)


def test_performance_routes_share_hw5_serializer_and_keep_query_counts(
    hw4_logged_in, hw4_session_factory, rental_payload, manager_payload,
):
    with hw4_session_factory() as db:
        offset = db.scalar(select(func.count()).select_from(Rental))
    manager = create_manager(hw4_logged_in, manager_payload)
    for manager_id in (manager['id'], manager['id'], None):
        create_rental(hw4_logged_in, {**rental_payload, 'managerId': manager_id})
    responses = [hw4_logged_in.get(f'/api/rentals/{version}', params={"page_size": 10, "offset": offset})
                 for version in ('naive', 'fixed')]
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()
    rows = responses[0].json()
    assert len(rows) == 3
    assert all({"listingCode", "availableUnits", "managerId", "createdAt", "updatedAt", "manager"}
               <= set(row) for row in rows)
    assert [row['managerId'] for row in rows] == [manager['id'], manager['id'], None]
    assert rows[-1]['manager'] is None
    assert int(responses[0].headers['X-Data-SQL-Statements']) == len(rows) + 1
    assert int(responses[1].headers['X-Data-SQL-Statements']) == 1


@pytest.mark.parametrize("column, value, error_code", [
    ("available_units", -1, 3819), ("listing_code", None, 1048),
])
def test_database_enforces_hw5_values_without_api_validation(
    hw4_logged_in, hw4_session_factory, rental_payload, column, value, error_code,
):
    row = create_rental(hw4_logged_in, rental_payload)
    with hw4_session_factory() as db:
        with pytest.raises(DBAPIError) as error:
            db.execute(text(f"UPDATE rentals SET {column}=:value WHERE id=:id"),
                       {"id": row["id"], "value": value})
        assert error.value.orig.args[0] == error_code
        db.rollback()
    assert hw4_logged_in.get(f'/api/rentals/{row["id"]}').json() == row


def test_default_pagination_is_bounded_and_total_is_not_page_size(hw4_logged_in, hw4_session_factory):
    with hw4_session_factory() as db:
        total = db.scalar(select(func.count()).select_from(Rental))
    response = hw4_logged_in.get('/api/rentals')
    assert len(response.json()) == min(50, total)
    assert response.headers['X-Total-Count'] == str(total)


def test_synthetic_legacy_contact_can_be_serialized_and_updated(hw4_logged_in, hw4_session_factory):
    with hw4_session_factory() as db:
        # Match the migration's documented contact format without depending on
        # any particular preexisting database row or modifying its identity.
        manager = PropertyManager(name='Legacy Manager', company='Legacy import',
                                  email=f'pending-{uuid4().hex}@example.com')
        db.add(manager)
        db.flush()
        manager_id = manager.id
        manager.email = f'legacy-manager-{manager_id}@example.com'
        db.commit()
    path = f'/api/property-managers/{manager_id}'
    before = hw4_logged_in.get(path).json()
    assert before['email'] == f'legacy-manager-{manager_id}@example.com'
    response = hw4_logged_in.put(path, json={
        'name': 'Updated Legacy Manager', 'company': 'New Legacy Company', 'email': before['email']})
    assert response.status_code == 200
    assert response.json()['email'] == before['email']
    assert response.json()['createdAt'] == before['createdAt']
