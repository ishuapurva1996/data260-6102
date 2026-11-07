"""Apply the semester database prerequisites, then HW9 migrations 006 and 007."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--seed-accounts", action="store_true")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    if not os.environ.get("HW4_DATABASE_URL"):
        parser.error("Set HW4_DATABASE_URL in the private environment file.")

    from web_application.database import db_session_basede26 as engine

    from scripts.hw04.db_setup import create_database, migrate
    from scripts.hw05.part1.db_setup import migrate as migrate_hw5
    from scripts.hw07.db_setup import migrate as migrate_hw7
    from scripts.hw07.db_setup import seed_accounts

    try:
        create_database()
        print("HW4/HW5 prerequisites:", migrate_hw5(engine))
        print("HW7 migration 005:", "applied" if migrate_hw7(engine) else "current")
        print("Numbered migrations through 007:", migrate(engine, through=7))
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


if __name__ == "__main__":
    raise SystemExit(main())
