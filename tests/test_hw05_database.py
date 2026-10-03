"""Real MySQL migration proof on an explicitly disposable, initially empty DB.

These tests run DDL, so savepoint fixtures cannot isolate them. They never use
HW4_DATABASE_URL/HW4_TEST_DATABASE_URL implicitly and refuse an occupied schema.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.hw04.db_setup import migrate as migrate_hw4
from scripts.hw05.part1.db_setup import migrate, seed_demo


OWNED_TABLES = (
    "sessions", "rentals", "property_managers", "users",
    "hw05_migration_progress", "schema_migrations",
)
ORIGINAL_COLUMNS = {
    "users": "id,name,email,password_hash",
    "sessions": "id,user_id,created_at,expires_at,last_activity_at",
    "property_managers": "id,name",
    "rentals": "id,listing_title,property_address,submitter_email,description,property_type,terms_accepted,manager_id",
}


@pytest.fixture(scope="module")
def migration_engine():
    raw = os.environ.get("HW5_MIGRATION_TEST_DATABASE_URL")
    if not raw or os.environ.get("HW5_ALLOW_DESTRUCTIVE_MIGRATION_TESTS") != "1":
        pytest.skip("Migration DDL tests require an explicitly disposable dedicated MySQL URL and opt-in")
    try:
        url = make_url(raw)
    except Exception:
        pytest.fail("Invalid migration-test URL", pytrace=False)
    if url.drivername != "mysql+pymysql" or url.database != "s6102_rel":
        pytest.fail("Migration tests require mysql+pymysql and s6102_rel", pytrace=False)
    engine = create_engine(
        url, hide_parameters=True,
        connect_args={"charset": "utf8mb4", "init_command": "SET time_zone = '+00:00'"},
    )
    if inspect(engine).get_table_names():
        engine.dispose()
        pytest.fail("Refusing migration tests: dedicated database must initially be empty", pytrace=False)
    try:
        yield engine
    finally:
        _drop_owned_tables(engine)
        engine.dispose()


def _drop_owned_tables(engine):
    with engine.begin() as connection:
        # The schema was verified empty before our first CREATE. Only our
        # named fixture tables are removed; foreign key checks stay enabled.
        for table in OWNED_TABLES:
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS `{table}`")


@pytest.fixture
def populated_hw4(migration_engine):
    _drop_owned_tables(migration_engine)
    migrate_hw4(migration_engine, through=3)
    with migration_engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users VALUES (91, 'Original user', 'original@example.com', "
            "'$argon2id$preserve-this-stored-hash-byte-for-byte')"
        )
        connection.exec_driver_sql(
            "INSERT INTO sessions VALUES ('CaseSensitive-Session-91',91,"
            "'2026-01-01 12:00:00.000001','2030-01-01 12:00:00.000001','2026-01-01 12:05:00.000002')"
        )
        connection.exec_driver_sql("INSERT INTO property_managers VALUES (70,'Original manager'),(71,'Unused manager')")
        connection.exec_driver_sql(
            "INSERT INTO rentals VALUES "
            "(901,'Straße original','10 Original Avenue','owner@example.com',"
            "'Original description remains exactly as stored.','apartment',1,70),"
            "(903,'Unassigned original','12 Original Avenue','other@example.com',"
            "'Another original description remains unchanged.','house',1,NULL)"
        )
    return migration_engine


def _original_rows(engine):
    with engine.connect() as connection:
        return {
            table: [tuple(row) for row in connection.exec_driver_sql(f"SELECT {columns} FROM {table} ORDER BY id")]
            for table, columns in ORIGINAL_COLUMNS.items()
        }


def _all_rows(engine):
    with engine.connect() as connection:
        return {
            table: [tuple(row) for row in connection.exec_driver_sql(f"SELECT * FROM {table} ORDER BY id")]
            for table in ORIGINAL_COLUMNS
        }


def _old_indexes(engine):
    return {
        table: {entry["name"]: (entry["column_names"], entry["unique"])
                for entry in inspect(engine).get_indexes(table)}
        for table in ORIGINAL_COLUMNS
    }


def test_populated_upgrade_preserves_all_original_values_and_indexes(populated_hw4):
    engine = populated_hw4
    before = _original_rows(engine)
    indexes = _old_indexes(engine)
    lower_bound = datetime.now(timezone.utc).replace(tzinfo=None)
    assert migrate(engine) == ["004_hw5_related_entities"]
    upper_bound = datetime.now(timezone.utc).replace(tzinfo=None)
    assert _original_rows(engine) == before
    for table, entries in indexes.items():
        assert _old_indexes(engine)[table].items() >= entries.items()
    with engine.connect() as connection:
        managers = connection.exec_driver_sql("SELECT id,company,email,created_at,updated_at FROM property_managers ORDER BY id").all()
        for manager in managers:
            assert manager.company == "Legacy import"
            assert manager.email == f"legacy-manager-{manager.id}@example.com"
            assert lower_bound <= manager.created_at <= upper_bound
            assert manager.updated_at == manager.created_at
        rentals = connection.exec_driver_sql("SELECT id,listing_code,available_units,created_at,updated_at FROM rentals ORDER BY id").all()
        for rental in rentals:
            assert rental.listing_code == f"S6102-R-{rental.id}"
            assert rental.available_units == 1
            assert rental.created_at == managers[0].created_at == rental.updated_at
        assert connection.exec_driver_sql("SELECT version FROM schema_migrations ORDER BY version").scalars().all() == [1, 3, 4]
    preserved = _all_rows(engine)
    assert migrate(engine) == []
    assert _all_rows(engine) == preserved


@pytest.mark.parametrize("interrupted_step", [
    "add:property_managers:company", "add:rentals:listing_code",
    "backfill:property_managers", "constrain:rentals:listing_code",
    "foreign-key:drop", "foreign-key:add", "journal",
])
def test_resume_after_committed_ddl_or_backfill(populated_hw4, interrupted_step):
    engine = populated_hw4
    before = _original_rows(engine)

    def interrupt(step):
        if step == interrupted_step:
            raise RuntimeError("deliberate simulated interruption")

    with pytest.raises(RuntimeError, match="deliberate simulated interruption"):
        migrate(engine, after_step=interrupt)
    assert _original_rows(engine) == before
    with engine.connect() as connection:
        started_at = connection.exec_driver_sql("SELECT started_at FROM hw05_migration_progress WHERE version=4").scalar_one()
    migrate(engine)
    assert _original_rows(engine) == before
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT DISTINCT created_at FROM rentals").scalars().all() == [started_at]
        assert connection.exec_driver_sql("SELECT DISTINCT created_at FROM property_managers").scalars().all() == [started_at]
    assert migrate(engine) == []


def test_final_database_constraints_reject_invalid_writes(populated_hw4):
    engine = populated_hw4
    migrate(engine)
    bad_statements = [
        "UPDATE rentals SET available_units=-1 WHERE id=901",
        "UPDATE rentals SET listing_code=NULL WHERE id=901",
        "UPDATE rentals SET listing_code='S6102-R-901' WHERE id=903",
        "UPDATE rentals SET manager_id=999999 WHERE id=901",
        "UPDATE property_managers SET email='legacy-manager-70@example.com' WHERE id=71",
        "DELETE FROM property_managers WHERE id=70",
    ]
    before = _all_rows(engine)
    for sql in bad_statements:
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.exec_driver_sql(sql)
        assert _all_rows(engine) == before
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM property_managers WHERE id=71")
        connection.exec_driver_sql(
            "INSERT INTO rentals (listing_title,property_address,submitter_email,description,property_type,terms_accepted,listing_code) "
            "VALUES ('New default','14 Example Road','owner@example.com','A valid description long enough for the database.','condo',1,'S6102-R-9999')"
        )
        row = connection.exec_driver_sql("SELECT id,available_units,created_at,updated_at,manager_id FROM rentals WHERE listing_code='S6102-R-9999'").one()
        assert row.id > 903 and row.available_units == 1 and row.manager_id is None
        assert row.created_at is not None and row.updated_at is not None


def test_upgrade_does_not_add_optional_historical_index(migration_engine):
    _drop_owned_tables(migration_engine)
    migrate(migration_engine)
    assert "ix_rentals_listing_title" not in _old_indexes(migration_engine)["rentals"]
    assert seed_demo(migration_engine) == 1
    before = _all_rows(migration_engine)
    assert seed_demo(migration_engine) == 0
    assert _all_rows(migration_engine) == before
    with migration_engine.connect() as connection:
        row = connection.exec_driver_sql("SELECT id,listing_code FROM rentals").one()
        assert row.listing_code == f"S6102-R-{row.id}"


def test_applied_migration_checksum_is_guarded(populated_hw4):
    engine = populated_hw4
    migrate(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE schema_migrations SET checksum=:value WHERE version=4"), {"value": "0" * 64})
    with pytest.raises(RuntimeError, match="Applied migration 004 has changed"):
        migrate(engine)
