"""Create/replay only owned MySQL study fixtures and freeze public task cases."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]

from web_application.models import PropertyManager, Rental

from scripts.hw06.runtime_lease import RuntimeLease
from src.rental_tools.executor import execute_tool
from src.rental_tools.reader import MySQLRentalReader
from src.rental_tools.service import RentalService

QUERY = "HW7 6102 Garden"
MANAGER_EMAIL = "hw7-6102-agent-fixture@example.com"
MISSING_ID = 2147483000
ROWS = [
    (
        "Apartment",
        "101 Course Garden Lane",
        "apartment",
        "A bright apartment beside a community garden.",
    ),
    ("House", "202 Course Garden Lane", "house", "A detached house with a fenced private garden."),
    (
        "Downtown Condo",
        "303 Course Market Street",
        "condo",
        "A compact condo near the downtown public library.",
    ),
]


def seed(engine, frozen=None):
    """Preserve old rows; refuse collisions instead of replacing any data."""
    with Session(engine) as db, db.begin():
        manager = db.scalar(select(PropertyManager).where(PropertyManager.email == MANAGER_EMAIL))
        if manager is None:
            fields = {"id": frozen["fixture"]["manager_id"]} if frozen else {}
            manager = PropertyManager(
                **fields,
                name="HW7 6102 Study Manager",
                company="Course fixture",
                email=MANAGER_EMAIL,
            )
            db.add(manager)
            db.flush()
        elif frozen is None or manager.id != frozen["fixture"]["manager_id"]:
            raise RuntimeError("Study manager collision; retain the existing snapshot.")
        for index, (title, address, kind, description) in enumerate(ROWS, 1):
            rental_id = frozen["fixture"]["rentals"][index - 1]["id"] if frozen else None
            row = db.get(Rental, rental_id) if rental_id is not None else None
            if row is None:
                fields = {"id": frozen["fixture"]["rentals"][index - 1]["id"]} if frozen else {}
                row = Rental(
                    **fields,
                    listing_code=f"S6102-R-{rental_id or (266102000 + index)}",
                    listing_title=(QUERY + " " + title if index < 3 else "HW7 6102 " + title),
                    property_address=address,
                    property_type=kind,
                    description=description,
                    terms_accepted=True,
                    submitter_email="hw7-fixture@example.com",
                    manager_id=manager.id,
                )
                db.add(row)
                db.flush()
                row.listing_code = f"S6102-R-{row.id}"
            elif row.listing_code != f"S6102-R-{row.id}" or row.manager_id != manager.id:
                raise RuntimeError("Study listing collision; no row was overwritten.")
        manager_id = manager.id
    reader = MySQLRentalReader(os.environ["HW4_DATABASE_URL"])
    service = RentalService(reader)
    try:

        def invoke(name, **inputs):
            result = json.loads(execute_tool(name, inputs, service=service))
            if not result["ok"]:
                raise RuntimeError("Fixture read failed.")
            return result["data"]

        found = invoke("search_rentals", query=QUERY, limit=5)["items"]
        details = [invoke("get_rental", rental_id=row["id"]) for row in found]
        all_rows = details + [
            invoke("get_rental", rental_id=row.id) for row in _condos(engine, manager_id)
        ]
        count = invoke("count_rentals", manager_id=manager_id)["count"]
        if len(found) != 2 or count != 3 or reader.get_rental(MISSING_ID) is not None:
            raise RuntimeError("Fixture assertions failed.")
        return manager_id, found, details, all_rows
    finally:
        reader.close()


def _condos(engine, manager_id):
    with Session(engine) as db:
        return list(
            db.scalars(
                select(Rental).where(
                    Rental.manager_id == manager_id, Rental.property_type == "condo"
                )
            )
        )


def freeze(engine, destination):
    frozen = json.loads(destination.read_text()) if destination.exists() else None
    manager, found, details, all_rows = seed(engine, frozen)
    shape = (
        'Return only one JSON object with keys "rentals" and "count". Each rental '
        "must copy id, listingTitle, propertyAddress, propertyType and managerId from tools. "
    )
    tasks = [
        {
            "id": "A",
            "query": QUERY,
            "manager_id": manager,
            "prompt": f"Search rentals for the literal term '{QUERY}' with limit 5, then get full "
            "details for the FIRST returned rental. "
            + shape
            + 'Include its description, emit exactly that one rental, and use "count": null. '
            "Complete the tool chain from this single instruction; do not ask a follow-up.",
            "expected": {"rentals": details[:1], "count": None},
        },
        {
            "id": "B",
            "query": QUERY,
            "manager_id": manager,
            "prompt": f"Count rentals for manager {manager}, then search the literal term '{QUERY}' "
            f"with limit 5 and select ONE supporting example belonging to manager {manager}. "
            + shape
            + "Use the observed integer count and exactly one example, without a description. "
            "Complete both tool operations from this single instruction; do not ask a follow-up.",
            "expected": {"rentals": found, "count": 3},
        },
        {
            "id": "C",
            "query": QUERY,
            "manager_id": manager,
            "prompt": f"Search rentals for the literal term '{QUERY}' with limit 5. Get full details "
            "for BOTH of the first two returned rentals to compare their public fields. "
            + shape
            + 'Include both descriptions, emit the two rentals in search order, and use "count": null. '
            "Complete all three tool operations from this single instruction; do not ask a follow-up.",
            "expected": {"rentals": details, "count": None},
        },
    ]
    data = {
        "schema_version": 1,
        "sid4": 6102,
        "seed": 6102,
        "verify_seed": 266102,
        "fixture": {"manager_id": manager, "query": QUERY, "rentals": all_rows},
        "tasks": tasks,
        "missing_id": MISSING_ID,
    }
    if frozen is not None:
        if data != frozen:
            raise RuntimeError("Frozen cases changed; do not silently replace scored inputs.")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x") as stream:
            stream.write(json.dumps(data, indent=2) + "\n")
    return data


def cleanup(engine, frozen):
    """Delete only the exact frozen course fixtures, never historical records."""
    with Session(engine) as db, db.begin():
        for index, expected in enumerate(frozen["fixture"]["rentals"], 1):
            row = db.get(Rental, expected["id"])
            if row is not None:
                if (
                    row.listing_code != f"S6102-R-{row.id}"
                    or row.manager_id != frozen["fixture"]["manager_id"]
                ):
                    raise RuntimeError("Cleanup ownership mismatch.")
                db.delete(row)
        db.flush()
        manager = db.get(PropertyManager, frozen["fixture"]["manager_id"])
        if manager is not None:
            if manager.email != MANAGER_EMAIL:
                raise RuntimeError("Cleanup manager ownership mismatch.")
            db.delete(manager)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/hw07/cases/agent_tasks.json")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    engine = create_engine(os.environ["HW4_DATABASE_URL"], hide_parameters=True)
    try:
        with RuntimeLease(args.runtime_dir, owner="HW7-cases", purpose="controlled rental fixture"):
            if args.cleanup:
                cleanup(engine, json.loads(args.output.read_text()))
                print("Pragya Apurva | removed only frozen HW7 fixture rows")
            else:
                data = freeze(engine, args.output)
                print(
                    "Pragya Apurva | frozen real MySQL A/B/C cases | manager",
                    data["fixture"]["manager_id"],
                    "| rental IDs",
                    [r["id"] for r in data["fixture"]["rentals"]],
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
