"""Add HW7 username/role fields and seed private teaching accounts explicitly."""

import argparse
import hashlib
import os
import sys
from pathlib import Path

from argon2 import PasswordHasher
from dotenv import load_dotenv
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))


def migrate(engine):
    source = ROOT / "code/web_application/migrations/005_users_jwt.sql"
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    sql = "\n".join(
        line for line in source.read_text().splitlines() if not line.lstrip().startswith("--")
    )
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with engine.begin() as db:
        if not {"users", "schema_migrations"} <= set(inspect(db).get_table_names()):
            raise RuntimeError("Apply the HW4 and HW5 baseline migrations first.")
        previous = db.execute(
            text("SELECT checksum FROM schema_migrations WHERE version=5")
        ).scalar()
        if previous:
            if previous != checksum:
                raise RuntimeError("Applied migration 005 changed; add a new migration.")
            return False
        columns = {c["name"]: c for c in inspect(db).get_columns("users")}
        if "username" not in columns:
            db.exec_driver_sql(statements[0])
        if "role" not in columns:
            db.exec_driver_sql(statements[1])
        db.exec_driver_sql(statements[2])
        db.exec_driver_sql(statements[3])
        unique = {c["name"] for c in inspect(db).get_unique_constraints("users")}
        if "uq_users_username" not in unique:
            db.exec_driver_sql(statements[4])
        constraints = {c["name"] for c in inspect(db).get_check_constraints("users")}
        for name, statement in zip(("ck_users_role", "ck_users_username"), statements[5:]):
            if name not in constraints:
                db.exec_driver_sql(statement)
        db.execute(
            text("INSERT INTO schema_migrations (version,name,checksum) VALUES (5,:name,:hash)"),
            {"name": source.name, "hash": checksum},
        )
    return True


def seed_accounts(engine):
    from web_application.models import User
    from web_application.routers.auth import LoginInput

    results = {}
    with Session(engine) as db, db.begin():
        for role in ("reader", "writer", "moderator"):
            prefix = f"HW7_{role.upper()}_"
            payload = LoginInput(
                username=os.environ[prefix + "USERNAME"], password=os.environ[prefix + "PASSWORD"]
            )
            row = db.scalar(select(User).where(User.username == payload.username))
            if row is not None:
                if row.role != role or row.email != f"{payload.username}@example.com":
                    raise RuntimeError("Teaching username is already owned by a different account.")
                if not PasswordHasher().verify(row.password_hash, payload.password):
                    raise RuntimeError("Existing teaching account uses different credentials.")
                results[role] = "preserved"
            else:
                db.add(
                    User(
                        username=payload.username,
                        role=role,
                        name=f"Pragya Apurva ({role})",
                        email=f"{payload.username}@example.com",
                        password_hash=PasswordHasher().hash(payload.password),
                    )
                )
                results[role] = "created"
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--seed-accounts", action="store_true")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    from web_application.database import db_session_basede26 as engine

    try:
        print("Migration 005:", "applied" if migrate(engine) else "already current")
        if args.seed_accounts:
            print("Teaching accounts:", seed_accounts(engine))
    except (SQLAlchemyError, ValueError, RuntimeError, KeyError) as error:
        print(
            f"Setup failed ({type(error).__name__}); inspect private configuration/schema.",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
