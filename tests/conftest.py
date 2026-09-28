"""HW4 integration fixtures: real, explicitly configured MySQL only.

Every test opens an outer connection transaction. Request sessions use nested
savepoints, so application commits are exercised but fixture teardown rolls back
all inserted/updated/deleted rows. MySQL may still consume AUTO_INCREMENT values.
No database, schema, seed account, or production row is created outside that
transaction. Run migrations separately before opting in with
HW4_TEST_DATABASE_URL (preferred) or an explicit HW4_DATABASE_URL.
"""
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))



class Clock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture(scope="session")
def hw4_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    raw = os.environ.get("HW4_TEST_DATABASE_URL") or os.environ.get("HW4_DATABASE_URL")
    if not raw:
        pytest.skip("Real MySQL checks require explicit HW4_TEST_DATABASE_URL or HW4_DATABASE_URL")
    try:
        url = make_url(raw)
    except Exception:
        pytest.fail("The configured HW4 test database URL is invalid", pytrace=False)
    if url.drivername != "mysql+pymysql" or url.database != "s6102_rel":
        pytest.fail("HW4 tests require mysql+pymysql and database s6102_rel", pytrace=False)
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True,
                           connect_args={"charset": "utf8mb4", "init_command": "SET time_zone = '+00:00'"})
    yield engine
    engine.dispose()


@pytest.fixture
def hw4_session_factory(hw4_engine):
    from sqlalchemy.orm import sessionmaker
    connection = hw4_engine.connect()
    outer_transaction = connection.begin()
    factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint",
                           expire_on_commit=False)
    try:
        yield factory
    finally:
        if outer_transaction.is_active:
            outer_transaction.rollback()
        connection.close()


@pytest.fixture(scope="session")
def hw4_password_hash():
    from argon2 import PasswordHasher
    # A test-only credential, hashed once to keep the suite practical.
    return PasswordHasher().hash("local-test-password-6102")


@pytest.fixture
def hw4_user(hw4_session_factory, hw4_password_hash):
    from web_application.models import User
    with hw4_session_factory() as db:
        user = User(name="HW4 test user", email=f"hw4-{uuid4().hex}@example.com",
                    password_hash=hw4_password_hash)
        db.add(user)
        db.commit()
        return {"id": user.id, "name": user.name, "email": user.email,
                "password": "local-test-password-6102"}


@pytest.fixture
def hw4_clock():
    return Clock()


@pytest.fixture
def hw4_app(hw4_session_factory, hw4_clock, tmp_path):
    from web_application.main import create_app
    return create_app(session_factory=hw4_session_factory, clock=hw4_clock,
                      frontend_dist=tmp_path / "missing-dist")


@pytest.fixture
def hw4_client(hw4_app):
    from fastapi.testclient import TestClient
    with TestClient(hw4_app, base_url="https://testserver") as client:
        yield client


@pytest.fixture
def hw4_logged_in(hw4_client, hw4_user):
    response = hw4_client.post("/api/auth/login", json={
        "email": hw4_user["email"], "password": hw4_user["password"]})
    assert response.status_code == 200
    return hw4_client


@pytest.fixture
def rental_payload():
    return {"listingTitle": f"Test rental {uuid4().hex}",
            "propertyAddress": "10 Orchard Avenue, San Jose, CA",
            "submitterEmail": "owner@example.com",
            "description": "A bright rental home with a spacious living room.",
            "propertyType": "apartment", "termsAccepted": True}
