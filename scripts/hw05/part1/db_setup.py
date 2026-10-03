#!/usr/bin/env python3
"""Explicit HW5 MySQL setup. Preserve populated HW4 data and resume safely."""

import argparse
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "code"))

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from scripts.hw04.db_setup import create_database, seed_account
from scripts.hw05.part1.migration_004 import upgrade
from web_application.database import db_session_basede26


def migrate(engine=db_session_basede26, *, after_step=None):
    """Run HW5 migration 004, creating the historical base only if needed."""
    return upgrade(engine, after_step=after_step)


def seed_demo(engine=db_session_basede26) -> int:
    """Add one manager/listing only when both domain tables are empty."""
    with engine.begin() as connection:
        occupied = connection.exec_driver_sql(
            "SELECT (SELECT COUNT(*) FROM rentals) + (SELECT COUNT(*) FROM property_managers)"
        ).scalar_one()
        if occupied:
            return 0
        manager = connection.execute(text(
            "INSERT INTO property_managers (name,company,email) "
            "VALUES (:name,:company,:email)"
        ), {"name": "Pragya Demo Manager", "company": "Campus Rental Demo", "email": "demo-manager-6102@example.com"})
        rental = connection.execute(text(
            "INSERT INTO rentals (listing_title,property_address,submitter_email,description,"
            "property_type,terms_accepted,manager_id,listing_code,available_units) "
            "VALUES (:title,:address,:email,:description,'apartment',1,:manager_id,:placeholder,1)"
        ), {
            "title": "Sunny Campus Apartment", "address": "6102 Example Avenue, San Jose, CA",
            "email": "demo-owner@example.com", "description": "A demonstration apartment close to campus and public transit.",
            "manager_id": manager.lastrowid, "placeholder": f"pending-{uuid4().hex}",
        })
        connection.execute(text("UPDATE rentals SET listing_code=:code WHERE id=:id"),
                           {"code": f"S6102-R-{rental.lastrowid}", "id": rental.lastrowid})
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-database", action="store_true")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--seed-demo", action="store_true", help="Seed one manager/listing only if both domain tables are empty.")
    parser.add_argument("--seed-account", action="store_true", help="Read HW4_SEED_NAME/EMAIL/PASSWORD privately.")
    args = parser.parse_args()
    if not any((args.create_database, args.migrate, args.seed_demo, args.seed_account)):
        parser.print_help()
        return 0
    if not os.environ.get("HW4_DATABASE_URL"):
        print("Explicit HW4_DATABASE_URL is required; select your owned instance.", file=sys.stderr)
        return 1
    try:
        if args.create_database:
            create_database()
            print("Database s6102_rel available; existing rows preserved.")
        if args.migrate:
            changed = migrate()
            print("Applied migrations: " + (", ".join(changed) if changed else "none; already current"))
        if args.seed_demo:
            print(f"Inserted HW5 demo manager/listing pairs: {seed_demo()}")
        if args.seed_account:
            created = seed_account(
                name=os.environ.get("HW4_SEED_NAME", ""),
                email=os.environ.get("HW4_SEED_EMAIL", ""),
                password=os.environ.get("HW4_SEED_PASSWORD", ""),
            )
            print("Teaching account created." if created else "Existing account preserved.")
    except SQLAlchemyError as exc:
        print(f"HW5 setup failed ({type(exc).__name__}); inspect local configuration/schema.", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        db_session_basede26.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
