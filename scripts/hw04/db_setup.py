#!/usr/bin/env python3
"""Explicit, repeatable MySQL schema setup and optional development seeds.

Nothing here runs during application startup. Credentials come from environment
variables; neither the database URL nor passwords are printed or CLI arguments.
"""

import argparse
import hashlib
import os
from pathlib import Path
import sys

from argon2 import PasswordHasher
from email_validator import validate_email
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "code"))

from web_application.database import DATABASE_NAME, db_session_basede26, get_database_url
from web_application.models import Rental, User


MIGRATIONS_DIRECTORY = REPOSITORY_ROOT / "code" / "web_application" / "migrations"


def create_database() -> None:
    """Create the configured assignment database if absent; preserve existing data."""
    admin_engine = create_engine(
        get_database_url()._replace(database=None),
        hide_parameters=True,
        connect_args={"charset": "utf8mb4", "init_command": "SET time_zone = '+00:00'"},
    )
    try:
        with admin_engine.begin() as connection:
            # DATABASE_NAME is an internal constant, never caller-provided SQL.
            connection.exec_driver_sql(
                f"CREATE DATABASE IF NOT EXISTS `{DATABASE_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        admin_engine.dispose()


def migrate(engine: Engine = db_session_basede26, *, through: int = 1) -> list[str]:
    """Apply unapplied numbered SQL migrations through a chosen version.

MySQL DDL commits implicitly. Scripts must therefore be additive and safe to
rerun after a partial failure. The journal is updated only after a script has
finished; checksums prohibit editing a migration already recorded as applied.
The default excludes Part 3's optional index migration until its experiment.
"""
    if through < 1:
        raise ValueError("Migration version must be at least 1.")
    migration_files = sorted(MIGRATIONS_DIRECTORY.glob("[0-9][0-9][0-9]_*.sql"))
    versions = [int(path.name.split("_", 1)[0]) for path in migration_files]
    if len(versions) != len(set(versions)):
        raise RuntimeError("Migration versions must be unique.")
    if through not in versions:
        raise ValueError(f"Migration version {through:03d} is unavailable.")

    applied: list[str] = []
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER NOT NULL PRIMARY KEY, "
            "name VARCHAR(255) NOT NULL, checksum CHAR(64) NOT NULL, "
            "applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
        for migration_file, version in zip(migration_files, versions):
            if version > through:
                continue
            source = migration_file.read_text(encoding="utf-8")
            checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()
            previous = connection.execute(
                text("SELECT checksum FROM schema_migrations WHERE version = :version"),
                {"version": version},
            ).scalar_one_or_none()
            if previous is not None:
                if previous != checksum:
                    raise RuntimeError(f"Applied migration {version:03d} has changed; add a new migration.")
                continue
            # These migrations contain simple DDL, not procedures or strings
            # containing semicolons. Strip whole-line comments before splitting.
            sql = "\n".join(
                line for line in source.splitlines() if not line.lstrip().startswith("--")
            )
            for statement in sql.split(";"):
                if statement.strip():
                    connection.exec_driver_sql(statement.strip())
            connection.execute(
                text(
                    "INSERT INTO schema_migrations (version, name, checksum) "
                    "VALUES (:version, :name, :checksum)"
                ),
                {"version": version, "name": migration_file.name, "checksum": checksum},
            )
            applied.append(migration_file.name)
    return applied


def seed_demo(engine: Engine = db_session_basede26) -> int:
    """Insert the two old demonstration records only when rentals is empty."""
    with Session(engine) as session, session.begin():
        if session.scalar(select(func.count()).select_from(Rental)):
            return 0
        session.add_all(
            [
                Rental(
                    listing_title="Sunny Downtown Apartment",
                    property_address="123 San Carlos Street, San Jose, CA",
                    submitter_email="downtown@example.com",
                    description="A bright apartment close to campus, shops, and public transit.",
                    property_type="apartment",
                    terms_accepted=True,
                ),
                Rental(
                    listing_title="Spacious Garden House",
                    property_address="456 Willow Street, San Jose, CA",
                    submitter_email="garden@example.com",
                    description="A comfortable house with a private garden and a sunny living room.",
                    property_type="house",
                    terms_accepted=True,
                ),
            ]
        )
    return 2


def seed_account(
    engine: Engine = db_session_basede26, *, name: str, email: str, password: str
) -> bool:
    """Create a normalized-email account; never overwrite an existing account."""
    name = name.strip()
    if not name or len(name) > 255:
        raise ValueError("HW4_SEED_NAME must contain 1–255 characters.")
    try:
        email = validate_email(email.strip(), check_deliverability=False).normalized.casefold()
    except ValueError:
        raise ValueError("HW4_SEED_EMAIL must be a valid email address.") from None
    if len(email) > 320:
        raise ValueError("HW4_SEED_EMAIL is too long.")
    if not password:
        raise ValueError("HW4_SEED_PASSWORD must be supplied outside tracked source.")
    with Session(engine) as session, session.begin():
        if session.scalar(select(User.id).where(User.email == email)) is not None:
            return False
        session.add(User(name=name, email=email, password_hash=PasswordHasher().hash(password)))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-database", action="store_true", help="Create s6102_rel if absent.")
    parser.add_argument("--migrate", action="store_true", help="Apply schema migrations explicitly.")
    parser.add_argument("--through", type=int, default=1, help="Highest migration version (default: 1).")
    parser.add_argument("--seed-demo", action="store_true", help="Seed two rentals only if none exist.")
    parser.add_argument("--seed-account", action="store_true", help="Use HW4_SEED_NAME/EMAIL/PASSWORD.")
    args = parser.parse_args()
    if not any((args.create_database, args.migrate, args.seed_demo, args.seed_account)):
        parser.print_help()
        return 0
    try:
        if args.create_database:
            create_database()
            print("Database s6102_rel is available; existing data was preserved.")
        if args.migrate:
            applied = migrate(through=args.through)
            print("Applied migrations: " + (", ".join(applied) if applied else "none; already current"))
        if args.seed_demo:
            print(f"Inserted demonstration rentals: {seed_demo()}")
        if args.seed_account:
            created = seed_account(
                name=os.environ.get("HW4_SEED_NAME", ""),
                email=os.environ.get("HW4_SEED_EMAIL", ""),
                password=os.environ.get("HW4_SEED_PASSWORD", ""),
            )
            print("Teaching account created." if created else "Existing account preserved; no changes.")
    except SQLAlchemyError as exc:
        # SQL exception text can expose bound data; preserve only the class here.
        print(f"Database setup failed ({type(exc).__name__}); check local configuration and schema.", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        db_session_basede26.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
