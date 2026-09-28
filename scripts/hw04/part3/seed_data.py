"""Generate and insert the exact HW4 Part 3 dataset without destructive reseeding.

Only this script's CLI imports the foundation application. Pure generation and
validation remain usable before that foundation exists. The insertion path uses
the foundation's Engine, SessionLocal, and mapped models; it defines no schema.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys

try:
    from .ownership import OwnershipError, verify_engine_ownership
except ImportError:
    from ownership import OwnershipError, verify_engine_ownership


SEED = 6102
RENTAL_COUNT = 5000
MANAGER_COUNT = 200
PROPERTY_TYPES = ("apartment", "house", "condo", "townhouse")


def generate_dataset(seed: int = SEED) -> dict:
    """Return a stable, domain-valid dataset with exactly 25 rentals per manager."""
    rng = random.Random(seed)
    manager_ordinals = list(range(1, MANAGER_COUNT + 1)) * (RENTAL_COUNT // MANAGER_COUNT)
    rng.shuffle(manager_ordinals)
    streets = ("Cedar", "Willow", "Maple", "Oak", "Pine", "Elm", "Birch", "Laurel")
    neighborhoods = ("Downtown", "Rose Garden", "Willow Glen", "Japantown", "Alum Rock")
    managers = [{"ordinal": i, "name": f"HW4 Property Manager {i:03d}"} for i in range(1, MANAGER_COUNT + 1)]
    rentals = []
    for ordinal, manager_ordinal in enumerate(manager_ordinals, start=1):
        property_type = rng.choice(PROPERTY_TYPES)
        neighborhood = rng.choice(neighborhoods)
        rentals.append({
            "listing_title": f"HW4-{seed}-{ordinal:05d} {property_type.title()} in {neighborhood}",
            "property_address": f"{100 + ordinal} {rng.choice(streets)} Street, San Jose, CA 95112",
            "submitter_email": f"landlord{manager_ordinal:03d}@example.com",
            "description": f"Well maintained {property_type} in {neighborhood}, with a bright living area and convenient access to local amenities.",
            "property_type": property_type,
            "terms_accepted": True,
            "manager_ordinal": manager_ordinal,
        })
    return {"format_version": 1, "seed": seed, "managers": managers, "rentals": rentals}


def dataset_checksum(dataset: dict) -> str:
    canonical = json.dumps(dataset, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_dataset(dataset: dict) -> dict:
    rentals, managers = dataset["rentals"], dataset["managers"]
    manager_ordinals = {row["ordinal"] for row in managers}
    if len(rentals) != RENTAL_COUNT or len(managers) != MANAGER_COUNT or manager_ordinals != set(range(1, MANAGER_COUNT + 1)):
        raise ValueError("Dataset must contain 5,000 rentals and exactly 200 unique manager ordinals")
    counts = Counter(row["manager_ordinal"] for row in rentals)
    if set(counts) != manager_ordinals or set(counts.values()) != {25}:
        raise ValueError("Every rental must reference an existing manager, with exactly 25 rentals each")
    titles = set()
    for row in rentals:
        for field in ("listing_title", "property_address"):
            value = row[field]
            if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 255:
                raise ValueError(f"Invalid generated {field}")
        if len(row["description"]) < 26 or row["property_type"] not in PROPERTY_TYPES or row["terms_accepted"] is not True:
            raise ValueError("Generated rental violates the six-field domain contract")
        email = row["submitter_email"]
        if email.count("@") != 1 or not email.endswith("@example.com") or any(char.isspace() for char in email):
            raise ValueError("Invalid generated submitter email")
        titles.add(row["listing_title"])
    if len(titles) != RENTAL_COUNT:
        raise ValueError("Selective index demonstration requires unique generated listing titles")
    return {
        "rental_count": len(rentals), "manager_count": len(managers), "association_count": sum(counts.values()),
        "distinct_manager_count": len(counts), "rentals_per_manager_min": min(counts.values()),
        "rentals_per_manager_max": max(counts.values()), "unique_listing_title_count": len(titles),
    }


def assert_empty_seed_target(rental_count: int, manager_count: int) -> None:
    if rental_count != 0 or manager_count != 0:
        raise OwnershipError("Refusing seed: rentals and property_managers must both be empty; no reset/delete/drop is supported")


def seed_owned_database(*, engine, session_factory, rental_model, manager_model, ownership_manifest, schema_revision: str, dataset=None, evidence_writer=None) -> dict:
    """Insert into an empty verified instance, leaving existing auth rows untouched.

    The transaction is atomic. Even a verified disposable instance is never
    emptied automatically. Use a freshly provisioned owned instance for reruns.
    A supplied evidence writer runs before commit so a write failure rolls back
    the inserts instead of leaving a seeded database without its manifest.
    """
    from sqlalchemy import func, select, text

    if not schema_revision or not schema_revision.strip():
        raise ValueError("Record the imported foundation's schema revision")
    dataset = generate_dataset() if dataset is None else dataset
    if dataset.get("seed") != SEED:
        raise ValueError("The measured assignment seed must be 6102")
    validate_dataset(dataset)
    generated_checksum = dataset_checksum(dataset)
    ownership = verify_engine_ownership(engine, ownership_manifest)
    with session_factory() as session:
        with session.begin():
            journal = [dict(row) for row in session.execute(text(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            )).mappings()]
            if not journal or schema_revision not in {journal[-1]["name"], f"{journal[-1]['version']:03d}"}:
                raise ValueError("Supplied schema revision does not match the actual migration journal")
            migration_dir = Path(__file__).resolve().parents[3] / "code/web_application/migrations"
            for migration in journal:
                source = (migration_dir / migration["name"]).read_bytes()
                if hashlib.sha256(source).hexdigest() != migration["checksum"]:
                    raise ValueError("Live migration checksum differs from the imported source")
            rental_count = session.scalar(select(func.count()).select_from(rental_model))
            manager_count = session.scalar(select(func.count()).select_from(manager_model))
            assert_empty_seed_target(rental_count, manager_count)
            managers_by_ordinal = {}
            for row in dataset["managers"]:
                manager = manager_model(name=row["name"])
                session.add(manager)
                managers_by_ordinal[row["ordinal"]] = manager
            session.flush()
            for row in dataset["rentals"]:
                attributes = {key: value for key, value in row.items() if key != "manager_ordinal"}
                attributes["manager_id"] = managers_by_ordinal[row["manager_ordinal"]].id
                session.add(rental_model(**attributes))
            session.flush()
            actual_rental_count = session.scalar(select(func.count()).select_from(rental_model))
            actual_manager_count = session.scalar(select(func.count()).select_from(manager_model))
            distribution = session.execute(
                select(rental_model.manager_id, func.count()).group_by(rental_model.manager_id).order_by(rental_model.manager_id)
            ).all()
            if actual_rental_count != RENTAL_COUNT or actual_manager_count != MANAGER_COUNT or len(distribution) != MANAGER_COUNT or any(manager_id is None or count != 25 for manager_id, count in distribution):
                raise ValueError("Live dataset counts do not match the seed contract; transaction rolled back")
            title_count = session.scalar(select(func.count(func.distinct(rental_model.listing_title))))
            id_range = session.execute(select(func.min(rental_model.id), func.max(rental_model.id))).one()
            session.expire_all()
            stored_managers = session.scalars(select(manager_model).order_by(manager_model.id)).all()
            stored_rentals = session.scalars(select(rental_model).order_by(rental_model.id)).all()
            ordinal_by_id = {manager.id: ordinal for ordinal, manager in enumerate(stored_managers, start=1)}
            stored_dataset = {
                "format_version": 1, "seed": SEED,
                "managers": [{"ordinal": ordinal_by_id[row.id], "name": row.name} for row in stored_managers],
                "rentals": [{
                    "listing_title": row.listing_title, "property_address": row.property_address,
                    "submitter_email": row.submitter_email, "description": row.description,
                    "property_type": row.property_type, "terms_accepted": row.terms_accepted,
                    "manager_ordinal": ordinal_by_id[row.manager_id],
                } for row in stored_rentals],
            }
            stored_checksum = dataset_checksum(stored_dataset)
            if stored_checksum != generated_checksum or title_count != RENTAL_COUNT:
                raise ValueError("Stored values differ from the generated dataset; transaction rolled back")
            mysql_version = session.scalar(text("SELECT VERSION()"))
            evidence = {
                "format_version": 1, "seed": SEED, "generated_dataset_sha256": generated_checksum,
                "stored_dataset_sha256": stored_checksum,
                "seeded_at_utc": datetime.now(timezone.utc).isoformat(), "schema_revision": schema_revision,
                "ownership": ownership, "mysql_version": mysql_version, "schema_migrations": journal,
                "actual_counts": {"rentals": actual_rental_count, "property_managers": actual_manager_count,
                    "associated_rentals": sum(count for _, count in distribution), "distinct_managers": len(distribution),
                    "unique_listing_titles": title_count},
                "rental_id_range": {"min": id_range[0], "max": id_range[1]},
                "manager_distribution": [{"manager_id": manager_id, "rental_count": count} for manager_id, count in distribution],
                "selective_title": dataset["rentals"][0]["listing_title"],
                "auth_records_policy": "Existing users and sessions are preserved; seeder never writes either table.",
                "reset_policy": "No reset/delete/drop support. Nonempty target is refused.",
            }
            if evidence_writer is not None:
                evidence_writer(evidence)
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ownership-manifest", required=True, type=Path, help="External verified disposable-instance JSON")
    parser.add_argument("--schema-revision", required=True, help="Imported foundation migration revision, recorded in seed evidence")
    parser.add_argument("--output", required=True, type=Path, help="New seed-evidence JSON path (must not already exist)")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Seed evidence path already exists; preserve it and choose a new output path")
    repository = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repository / "code"))
    from web_application.database import SessionLocal, db_session_basede26
    from web_application.models import PropertyManager, Rental

    # Reserve the evidence destination before database writes. Never replace an
    # existing artifact; a bad/unwritable parent must fail before seeding starts.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        try:
            def write_evidence(evidence):
                json.dump(evidence, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())

            evidence = seed_owned_database(
                engine=db_session_basede26, session_factory=SessionLocal,
                rental_model=Rental, manager_model=PropertyManager,
                ownership_manifest=args.ownership_manifest, schema_revision=args.schema_revision,
                evidence_writer=write_evidence,
            )
        except BaseException:
            # Seed/manifest failures roll back the transaction and remove only
            # this invocation's exclusive reservation, allowing a safe retry.
            output.close()
            args.output.unlink(missing_ok=True)
            raise
    print(json.dumps({"seed_manifest": str(args.output), "actual_counts": evidence["actual_counts"], "generated_dataset_sha256": evidence["generated_dataset_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
