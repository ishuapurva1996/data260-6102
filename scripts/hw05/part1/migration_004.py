"""Resumable additive HW5 schema upgrade. Applied source is checksum protected.

Each DDL/DML step commits separately because MySQL DDL cannot be rolled back.
Fresh metadata, rather than an assumed phase number, decides what remains.
"""

from collections.abc import Callable
import hashlib
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, inspect, text
from sqlalchemy.engine import Connection, Engine


VERSION = 4
NAME = "004_hw5_related_entities"
LOCK_NAME = "s6102_rel:hw05-schema-upgrade"
COLUMNS = {
    "property_managers": {
        "company": "VARCHAR(255)", "email": "VARCHAR(320)",
        "created_at": "DATETIME(6)", "updated_at": "DATETIME(6)",
    },
    "rentals": {
        "listing_code": "VARCHAR(64)", "available_units": "INTEGER",
        "created_at": "DATETIME(6)", "updated_at": "DATETIME(6)",
    },
}


def _columns(connection: Connection, table: str) -> dict:
    return {column["name"]: column for column in inspect(connection).get_columns(table)}


def _validate_rows(connection: Connection) -> None:
    """Fail before enforcement instead of replacing unexpected existing data."""
    for table, columns in COLUMNS.items():
        missing = " OR ".join(f"`{name}` IS NULL" for name in columns)
        if connection.exec_driver_sql(f"SELECT COUNT(*) FROM `{table}` WHERE {missing}").scalar_one():
            raise RuntimeError(f"HW5 upgrade found unfilled values in {table}; repair before resuming.")
    checks = (
        ("property_managers", "CHAR_LENGTH(TRIM(company)) = 0 OR CHAR_LENGTH(TRIM(email)) = 0"),
        ("rentals", "available_units < 0 OR listing_code NOT REGEXP '^S6102-R-[1-9][0-9]*$'"),
    )
    for table, condition in checks:
        if connection.exec_driver_sql(f"SELECT COUNT(*) FROM `{table}` WHERE {condition}").scalar_one():
            raise RuntimeError(f"HW5 upgrade found invalid values in {table}; repair before resuming.")
    for table, column in (("property_managers", "email"), ("rentals", "listing_code")):
        if connection.exec_driver_sql(
            f"SELECT COUNT(*) FROM (SELECT `{column}` FROM `{table}` "
            f"GROUP BY `{column}` HAVING COUNT(*) > 1) AS duplicates"
        ).scalar_one():
            raise RuntimeError(f"HW5 upgrade found duplicate {column} values; repair before resuming.")
    if connection.exec_driver_sql(
        "SELECT COUNT(*) FROM rentals r LEFT JOIN property_managers p ON p.id=r.manager_id "
        "WHERE r.manager_id IS NOT NULL AND p.id IS NULL"
    ).scalar_one():
        raise RuntimeError("HW5 upgrade found orphan manager references; repair before resuming.")


def upgrade(engine: Engine, *, after_step: Callable[[str], None] | None = None) -> list[str]:
    """Upgrade a configured HW4 database without changing its original records.

    ``after_step`` is a test seam called after each durable step, used to prove
    recovery from interruption. It is not exposed as a destructive CLI option.
    Stop application writes while running this maintenance operation.
    """
    if engine.url.drivername != "mysql+pymysql" or engine.url.database != "s6102_rel":
        raise ValueError("HW5 migration requires mysql+pymysql and database s6102_rel.")
    checksum = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with engine.connect() as connection:
        acquired = connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": LOCK_NAME}).scalar_one()
        connection.commit()
        if acquired != 1:
            raise RuntimeError("Another HW5 migration owns this database; retry after it finishes.")
        try:
            return _upgrade_locked(connection, engine, checksum, after_step)
        finally:
            connection.rollback()
            connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": LOCK_NAME})
            connection.commit()


def _upgrade_locked(connection, engine, checksum, after_step):
    # Historical files remain untouched; initialize 001 only, preserving an
    # already-applied optional 003 index without silently adding it elsewhere.
    from scripts.hw04.db_setup import MIGRATIONS_DIRECTORY, migrate as migrate_hw4

    migrate_hw4(engine, through=1)
    applied_rows = connection.exec_driver_sql("SELECT version,checksum FROM schema_migrations").all()
    for version, previous in applied_rows:
        if version == VERSION and previous != checksum:
            raise RuntimeError("Applied migration 004 has changed; add a new migration.")
        for path in MIGRATIONS_DIRECTORY.glob(f"{version:03d}_*.sql"):
            if hashlib.sha256(path.read_bytes()).hexdigest() != previous:
                raise RuntimeError(f"Applied migration {version:03d} has changed; add a new migration.")
    if any(version == VERSION for version, _ in applied_rows):
        return []
    connection.commit()

    def step(sql, label, params=None):
        if params is None:
            connection.exec_driver_sql(sql)
        else:
            connection.execute(text(sql), params)
        connection.commit()
        if after_step is not None:
            after_step(label)

    step(
        "CREATE TABLE IF NOT EXISTS hw05_migration_progress ("
        "version INTEGER NOT NULL PRIMARY KEY, started_at DATETIME(6) NOT NULL"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
        "progress-table",
    )
    step(
        "INSERT INTO hw05_migration_progress (version,started_at) VALUES (4,UTC_TIMESTAMP(6)) "
        "ON DUPLICATE KEY UPDATE version=version",
        "progress-time",
    )
    started_at = connection.exec_driver_sql("SELECT started_at FROM hw05_migration_progress WHERE version=4").scalar_one()

    for table, definitions in COLUMNS.items():
        for column, definition in definitions.items():
            existing = _columns(connection, table).get(column)
            if existing is None:
                step(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition} NULL", f"add:{table}:{column}")
            else:
                actual_type = existing["type"]
                if definition.startswith("VARCHAR"):
                    compatible = isinstance(actual_type, String) and actual_type.length == int(definition[8:-1])
                elif definition == "INTEGER":
                    compatible = isinstance(actual_type, Integer) and not actual_type.unsigned
                else:
                    compatible = isinstance(actual_type, DateTime) and actual_type.fsp == 6
                if not compatible:
                    raise RuntimeError(f"Existing {table}.{column} has an incompatible type; repair before resuming.")

    step(
        "UPDATE property_managers SET company=COALESCE(company,'Legacy import'), "
        "email=COALESCE(email,CONCAT('legacy-manager-',id,'@example.com')), "
        "created_at=COALESCE(created_at,:started), updated_at=COALESCE(updated_at,:started) "
        "WHERE company IS NULL OR email IS NULL OR created_at IS NULL OR updated_at IS NULL",
        "backfill:property_managers", {"started": started_at},
    )
    step(
        "UPDATE rentals SET listing_code=COALESCE(listing_code,CONCAT('S6102-R-',id)), "
        "available_units=COALESCE(available_units,1), "
        "created_at=COALESCE(created_at,:started), updated_at=COALESCE(updated_at,:started) "
        "WHERE listing_code IS NULL OR available_units IS NULL OR created_at IS NULL OR updated_at IS NULL",
        "backfill:rentals", {"started": started_at},
    )
    _validate_rows(connection)
    for table, definitions in COLUMNS.items():
        for column, definition in definitions.items():
            default = "CURRENT_TIMESTAMP(6)" if column.endswith("_at") else "1" if column == "available_units" else None
            existing = _columns(connection, table)[column]
            current_default = str(existing["default"]).lower() if existing["default"] is not None else None
            if existing["nullable"] or current_default != (default.lower() if default else None):
                suffix = f" DEFAULT {default}" if default is not None else ""
                step(f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` {definition} NOT NULL{suffix}", f"constrain:{table}:{column}")

    for table, column, name in (
        ("property_managers", "email", "uq_property_managers_email"),
        ("rentals", "listing_code", "uq_rentals_listing_code"),
    ):
        indexes = {index["name"]: index for index in inspect(connection).get_indexes(table)}
        existing = indexes.get(name)
        if existing is None:
            step(f"ALTER TABLE `{table}` ADD CONSTRAINT `{name}` UNIQUE (`{column}`)", f"unique:{table}:{column}")
        elif existing["column_names"] != [column] or not existing["unique"]:
            raise RuntimeError(f"Existing index {name} is incompatible; repair before resuming.")

    checks = {entry["name"]: entry for entry in inspect(connection).get_check_constraints("rentals")}
    units_check = checks.get("ck_rentals_available_units")
    if units_check is None:
        step("ALTER TABLE rentals ADD CONSTRAINT ck_rentals_available_units CHECK (available_units >= 0)", "check:available_units")
    else:
        normalized = units_check["sqltext"].translate(str.maketrans("", "", "`() "))
        if normalized != "available_units>=0":
            raise RuntimeError("Existing available-units check is incompatible; repair before resuming.")

    for foreign_key in inspect(connection).get_foreign_keys("rentals"):
        if foreign_key["constrained_columns"] != ["manager_id"]:
            continue
        if foreign_key["referred_table"] != "property_managers" or foreign_key["referred_columns"] != ["id"]:
            raise RuntimeError("Existing manager foreign key is incompatible; repair before resuming.")
        if foreign_key.get("options", {}).get("ondelete", "RESTRICT").upper() in {"RESTRICT", "NO ACTION"}:
            break
        name = foreign_key["name"].replace("`", "``")
        step(f"ALTER TABLE rentals DROP FOREIGN KEY `{name}`", "foreign-key:drop")
    else:
        # The previous loop also reaches here after dropping the old SET NULL
        # constraint. A stopped process can safely resume with no FK present.
        step(
            "ALTER TABLE rentals ADD CONSTRAINT fk_rentals_manager FOREIGN KEY (manager_id) "
            "REFERENCES property_managers (id) ON DELETE RESTRICT",
            "foreign-key:add",
        )
    _validate_rows(connection)
    step(
        "INSERT INTO schema_migrations (version,name,checksum) VALUES (:version,:name,:checksum)",
        "journal", {"version": VERSION, "name": NAME, "checksum": checksum},
    )
    return [NAME]
