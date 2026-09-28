"""Real MySQL schema and transaction behavior; no DDL or destructive setup here."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import Depends
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import sessionmaker

from web_application import database
from web_application.database import get_db
from web_application.models import PropertyManager, Rental, SessionToken, User


def rental_values(payload):
    return {"listing_title": payload["listingTitle"], "property_address": payload["propertyAddress"],
            "submitter_email": payload["submitterEmail"], "description": payload["description"],
            "property_type": payload["propertyType"], "terms_accepted": payload["termsAccepted"]}


def test_required_engine_name_and_factory_binding():
    assert database.db_session_basede26.dialect.name == "mysql"
    assert database.db_session_basede26.url.database == "s6102_rel"
    assert database.SessionLocal.kw["bind"] is database.db_session_basede26


@pytest.mark.parametrize("url", ["sqlite:///:memory:", "mysql+pymysql://localhost/not_s6102", "not a URL"])
def test_connection_configuration_rejects_wrong_driver_or_database(monkeypatch, url):
    monkeypatch.setenv("HW4_DATABASE_URL", url)
    with pytest.raises(ValueError, match="HW4_DATABASE_URL"):
        database.get_database_url()


def test_real_mysql_has_required_schema_and_relations(hw4_engine):
    with hw4_engine.connect() as connection:
        assert connection.scalar(text("SELECT DATABASE()")) == "s6102_rel"
        inspector = inspect(connection)
        assert {"rentals", "users", "sessions", "property_managers"} <= set(inspector.get_table_names())
        rental_columns = {item["name"]: item for item in inspector.get_columns("rentals")}
        assert rental_columns["id"]["autoincrement"] is True
        assert rental_columns["listing_title"]["nullable"] is False
        assert rental_columns["property_address"]["nullable"] is False
        assert rental_columns["manager_id"]["nullable"] is True
        session_columns = {item["name"] for item in inspector.get_columns("sessions")}
        assert {"id", "user_id", "created_at", "expires_at", "last_activity_at"} <= session_columns
        assert any(item["constrained_columns"] == ["user_id"] and item["referred_table"] == "users"
                   for item in inspector.get_foreign_keys("sessions"))
        assert any(item["constrained_columns"] == ["manager_id"] and item["referred_table"] == "property_managers"
                   for item in inspector.get_foreign_keys("rentals"))
        assert any(item["column_names"] == ["email"] for item in inspector.get_unique_constraints("users"))


def test_unique_email_is_enforced_and_failed_write_rolls_back(hw4_session_factory, hw4_user, hw4_password_hash):
    with hw4_session_factory() as db:
        db.add(User(name="Duplicate", email=hw4_user["email"], password_hash=hw4_password_hash))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    with hw4_session_factory() as db:
        users = list(db.scalars(select(User).where(User.email == hw4_user["email"])))
        assert len(users) == 1
        assert users[0].name == hw4_user["name"]


@pytest.mark.parametrize("changes", [
    {"listing_title": None}, {"property_address": None}, {"listing_title": " "},
    {"description": "too short"}, {"property_type": "castle"}, {"terms_accepted": False},
])
def test_mysql_enforces_required_rental_values(hw4_session_factory, rental_payload, changes):
    values = {**rental_values(rental_payload), **changes}
    with hw4_session_factory() as db:
        before = list(db.scalars(select(Rental.id).order_by(Rental.id)))
        db.add(Rental(**values))
        # PyMySQL maps MySQL CHECK violation3819 to OperationalError;
        # NOT NULL violations1048 are IntegrityError. Assert exact DB errors.
        with pytest.raises(DBAPIError) as failure:
            db.commit()
        assert failure.value.orig.args[0] in {1048, 3819}
        db.rollback()
        assert list(db.scalars(select(Rental.id).order_by(Rental.id))) == before


def test_manager_foreign_key_rejects_missing_manager(hw4_session_factory, rental_payload):
    with hw4_session_factory() as db:
        missing_manager = max(db.scalars(select(PropertyManager.id)), default=0) + 1
        db.add(Rental(**rental_values(rental_payload), manager_id=missing_manager))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_manager_relation_round_trips_and_ordinary_rental_can_be_unassigned(hw4_session_factory, rental_payload):
    with hw4_session_factory() as db:
        manager = PropertyManager(name=f"Fixture manager {uuid4().hex}")
        assigned = Rental(**rental_values(rental_payload), manager=manager)
        unassigned = Rental(**rental_values(rental_payload))
        db.add_all([assigned, unassigned])
        db.commit()
        assigned_id, unassigned_id, manager_id = assigned.id, unassigned.id, manager.id
    with hw4_session_factory() as db:
        assert db.get(Rental, assigned_id).manager.id == manager_id
        assert db.get(Rental, unassigned_id).manager is None


def test_session_user_foreign_key_is_enforced(hw4_session_factory, hw4_clock):
    with hw4_session_factory() as db:
        missing_user = max(db.scalars(select(User.id)), default=0) + 1
        db.add(SessionToken(id=f"test-{uuid4().hex}", user_id=missing_user, created_at=hw4_clock(),
                            expires_at=hw4_clock(), last_activity_at=hw4_clock()))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_failed_request_rolls_back_flushed_changes_and_next_request_works(
    hw4_app, hw4_session_factory, rental_payload,
):
    values = rental_values(rental_payload)

    @hw4_app.post("/api/test-rollback")
    def failing_request(db=Depends(get_db)):
        db.add(Rental(**values))
        db.flush()
        raise RuntimeError("Deliberate rollback probe")

    with TestClient(hw4_app, base_url="https://testserver", raise_server_exceptions=False) as client:
        assert client.post("/api/test-rollback").status_code == 500
        assert client.get("/api/health").status_code == 200
    with hw4_session_factory() as db:
        assert db.scalar(select(Rental.id).where(Rental.listing_title == values["listing_title"])) is None


def test_application_commit_is_still_undone_by_fixture_outer_rollback(hw4_engine, rental_payload):
    # Demonstrates the fixture isolation mechanism on its own separate connection.
    marker = rental_payload["listingTitle"]
    with hw4_engine.connect() as connection:
        outer = connection.begin()
        factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            with factory() as db:
                row = Rental(**rental_values(rental_payload))
                db.add(row)
                db.commit()
                assert db.get(Rental, row.id) is not None
        finally:
            outer.rollback()
    with hw4_engine.connect() as connection:
        assert connection.scalar(select(Rental.id).where(Rental.listing_title == marker)) is None


def test_concurrent_database_inserts_receive_distinct_ids(hw4_engine, rental_payload):
    def insert_in_rolled_back_transaction(number):
        with hw4_engine.connect() as connection:
            outer = connection.begin()
            factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
            try:
                with factory() as db:
                    row = Rental(**{**rental_values(rental_payload),
                                    "listing_title": f'{rental_payload["listingTitle"]} concurrent {number}'})
                    db.add(row)
                    db.commit()
                    return row.id
            finally:
                outer.rollback()
    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(insert_in_rolled_back_transaction, [1, 2]))
    assert all(isinstance(value, int) and value > 0 for value in ids)
    assert len(set(ids)) == 2
