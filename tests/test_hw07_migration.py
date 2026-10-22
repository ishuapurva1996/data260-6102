"""Opt-in real MySQL DDL recovery in disposable, uniquely owned schemas."""

import hashlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text

from scripts.hw07.db_setup import ROOT, migrate


@pytest.fixture
def migration_database(hw4_password_hash):
    if os.environ.get("HW7_MIGRATION_TESTS") != "1":
        pytest.skip("Set HW7_MIGRATION_TESTS=1 to create/drop an isolated MySQL test schema")
    url = os.environ.get("HW7_MIGRATION_DATABASE_URL")
    if not url:
        pytest.fail(
            "HW7_MIGRATION_DATABASE_URL must explicitly identify a DDL-capable test administrator",
            pytrace=False,
        )
    admin_engine = create_engine(url, hide_parameters=True)
    name = "s6102_hw7_test_" + uuid4().hex
    created = False
    engine = create_engine(admin_engine.url.set(database=name), hide_parameters=True)
    try:
        with admin_engine.connect() as admin:
            admin.exec_driver_sql(f"CREATE DATABASE `{name}`")
            created = True
        with engine.begin() as db:
            db.exec_driver_sql(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, password_hash VARCHAR(255) NOT NULL)"
            )
            db.exec_driver_sql(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
                "name VARCHAR(255) NOT NULL, checksum CHAR(64) NOT NULL)"
            )
            db.execute(
                text("INSERT INTO users VALUES (1,:hash),(70,:hash)"), {"hash": hw4_password_hash}
            )
        yield engine
    finally:
        engine.dispose()
        if created:
            with admin_engine.connect() as admin:
                admin.exec_driver_sql(f"DROP DATABASE `{name}`")
        admin_engine.dispose()


@pytest.mark.parametrize("completed_steps", range(8))
def test_resume_after_each_implicitly_committed_ddl_step(
    migration_database, hw4_password_hash, completed_steps
):
    source = ROOT / "code/web_application/migrations/005_users_jwt.sql"
    sql = "\n".join(
        line for line in source.read_text().splitlines() if not line.lstrip().startswith("--")
    )
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    with migration_database.begin() as db:
        for statement in statements[:completed_steps]:
            db.exec_driver_sql(statement)
    assert migrate(migration_database) is True
    assert migrate(migration_database) is False
    with migration_database.connect() as db:
        rows = db.execute(
            text("SELECT id,username,role,password_hash FROM users ORDER BY id")
        ).all()
        assert [tuple(row) for row in rows] == [
            (1, "legacy_1", "reader", hw4_password_hash),
            (70, "legacy_70", "reader", hw4_password_hash),
        ]
        assert (
            db.scalar(text("SELECT checksum FROM schema_migrations WHERE version=5"))
            == hashlib.sha256(source.read_bytes()).hexdigest()
        )
        assert {c["name"] for c in inspect(db).get_check_constraints("users")} == {
            "ck_users_role",
            "ck_users_username",
        }
