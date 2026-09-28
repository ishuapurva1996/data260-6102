#!/usr/bin/env python3
"""Preserve one real MySQL listing-title index experiment after HTTP measurement.

The before state is accepted only without any leading listing-title index or
migration 003 journal entry. A rerun never drops an index to reconstruct a before
state. Each attempt gets a new directory, including failures and partial DDL.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

try:
    from .benchmark import revision_metadata
    from .ownership import OwnershipError, verify_engine_ownership
    from .seed_data import dataset_checksum
except ImportError:
    from benchmark import revision_metadata
    from ownership import OwnershipError, verify_engine_ownership
    from seed_data import dataset_checksum


REPOSITORY = Path(__file__).resolve().parents[3]
INDEX_NAME = "ix_rentals_listing_title"
QUERY = "SELECT id,listing_title FROM rentals WHERE listing_title=:title ORDER BY id"
MIGRATION = REPOSITORY / "code/web_application/migrations/003_listing_title_index.sql"


class IndexExperimentError(ValueError):
    def __init__(self, message, attempt_path=None):
        super().__init__(message)
        self.attempt_path = attempt_path


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported evidence type: {type(value).__name__}")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                               allow_nan=False, default=json_default) + "\n", encoding="utf-8")


def assert_unindexed(indexes, journal):
    """Fail closed, including alternative names, prefix indexes and composite keys."""
    for row in indexes:
        if row["Key_name"] == INDEX_NAME or (int(row["Seq_in_index"]) == 1 and row["Column_name"] == "listing_title"):
            raise IndexExperimentError("A listing-title index or the proposed index name already exists; refusing to relabel it as a before state")
    if any(int(row["version"]) == 3 for row in journal):
        raise IndexExperimentError("Migration 003 is already journaled; use preserved evidence or a new owned instance")


def capture_snapshot(engine, title):
    """Capture actual EXPLAIN output and data identity using the shared engine."""
    from sqlalchemy import text

    def mappings(connection, sql, parameters=None):
        return [dict(row) for row in connection.execute(text(sql), parameters or {}).mappings()]

    with engine.connect() as connection:
        indexes = mappings(connection, "SHOW INDEX FROM rentals")
        journal = mappings(connection, "SELECT version,name,checksum,applied_at FROM schema_migrations ORDER BY version")
        managers = mappings(connection, "SELECT id,name FROM property_managers ORDER BY id")
        rentals = mappings(connection, "SELECT id,listing_title,property_address,submitter_email,description,property_type,terms_accepted,manager_id FROM rentals ORDER BY id")
        ordinal_by_id = {row["id"]: ordinal for ordinal, row in enumerate(managers, start=1)}
        if any(row["manager_id"] not in ordinal_by_id for row in rentals):
            raise IndexExperimentError("Every benchmark rental must reference an existing manager")
        dataset = {
            "format_version": 1, "seed": 6102,
            "managers": [{"ordinal": ordinal_by_id[row["id"]], "name": row["name"]} for row in managers],
            "rentals": [{
                **{key: row[key] for key in ("listing_title", "property_address", "submitter_email", "description", "property_type")},
                "terms_accepted": bool(row["terms_accepted"]), "manager_ordinal": ordinal_by_id[row["manager_id"]],
            } for row in rentals],
        }
        parameters = {"title": title}
        result = mappings(connection, QUERY, parameters)
        traditional = mappings(connection, "EXPLAIN " + QUERY, parameters)
        format_json_raw = connection.execute(text("EXPLAIN FORMAT=JSON " + QUERY), parameters).scalar_one()
        # Validate the server's JSON without rewriting the raw output.
        json.loads(format_json_raw)
        server = dict(connection.execute(text("SELECT VERSION() AS version,@@server_uuid AS server_uuid,DATABASE() AS database_name")).mappings().one())
    return {
        "captured_at_utc": utc_now(), "query": QUERY, "parameters": parameters,
        "server": server, "indexes": indexes, "schema_migrations": journal,
        "dataset": {
            "stored_dataset_sha256": dataset_checksum(dataset),
            "physical_rows_sha256": dataset_checksum({"managers": managers, "rentals": rentals}),
            "counts": {
                "rentals": len(rentals), "property_managers": len(managers),
                "associated_rentals": sum(row["manager_id"] is not None for row in rentals),
                "distinct_managers": len({row["manager_id"] for row in rentals}),
                "unique_listing_titles": len({row["listing_title"] for row in rentals}),
            },
            "rental_id_range": {"min": rentals[0]["id"] if rentals else None, "max": rentals[-1]["id"] if rentals else None},
        },
        "results": result, "result_sha256": dataset_checksum(result),
        "explain_traditional": traditional, "explain_format_json_raw": format_json_raw,
    }


def validate_seed_identity(snapshot, seed, ownership):
    if seed.get("seed") != 6102:
        raise IndexExperimentError("The index experiment requires the recorded SEED 6102 dataset")
    if seed.get("ownership") != ownership:
        raise IndexExperimentError("Seed manifest belongs to a different owned database instance")
    identity = snapshot["dataset"]
    expected_counts = {"rentals": 5000, "property_managers": 200, "associated_rentals": 5000,
                       "distinct_managers": 200, "unique_listing_titles": 5000}
    if identity["counts"] != expected_counts or identity["counts"] != seed.get("actual_counts"):
        raise IndexExperimentError("Live dataset counts differ from the exact seed contract or seed manifest")
    if (identity["stored_dataset_sha256"] != seed.get("stored_dataset_sha256")
            or identity["stored_dataset_sha256"] != seed.get("generated_dataset_sha256")
            or identity["rental_id_range"] != seed.get("rental_id_range")):
        raise IndexExperimentError("Live dataset content or ID range differs from the seed manifest")
    server = snapshot["server"]
    if server["server_uuid"] != ownership.get("server_uuid") or server["database_name"] != "s6102_rel":
        raise IndexExperimentError("Snapshot was captured on a different MySQL instance")
    if snapshot["parameters"] != {"title": seed.get("selective_title")} or len(snapshot["results"]) != 1:
        raise IndexExperimentError("The exact seed title must return one rental for the selective equality experiment")


def compare_snapshots(before, after):
    for field in ("query", "parameters", "dataset", "results", "result_sha256"):
        if before[field] != after[field]:
            raise IndexExperimentError(f"Index experiment changed {field}; no valid before/after comparison")
    added = [row for row in after["indexes"] if row["Key_name"] == INDEX_NAME]
    if (len(added) != 1 or added[0]["Column_name"] != "listing_title"
            or int(added[0]["Seq_in_index"]) != 1 or added[0].get("Sub_part") is not None):
        raise IndexExperimentError("The expected new full-column listing-title index is missing or has a different definition")
    if not any(int(row["version"]) == 3 for row in after["schema_migrations"]):
        raise IndexExperimentError("Migration 003 is not journaled; preserve partial evidence and investigate")

    def observed(snapshot):
        return [{"table": row.get("table"), "access_type": row.get("type"),
                 "possible_keys": row.get("possible_keys"), "key": row.get("key"),
                 "rows": row.get("rows"), "filtered": row.get("filtered"), "extra": row.get("Extra")}
                for row in snapshot["explain_traditional"]]

    return {"query": before["query"], "parameters": before["parameters"],
            "equal_results": True, "equal_dataset": True, "result_sha256": before["result_sha256"],
            "before": observed(before), "after": observed(after),
            "interpretation_note": "Access type, key and rows are observed EXPLAIN fields. rows is an optimizer estimate, not an actual execution count or a measured latency."}


def save_snapshot(attempt, phase, snapshot):
    write_json(attempt / f"{phase}.json", snapshot)
    for key, name in (("explain_traditional", "explain"), ("indexes", "indexes"),
                      ("schema_migrations", "schema_migrations"), ("results", "results")):
        suffix = "_traditional" if key == "explain_traditional" else ""
        write_json(attempt / f"{name}_{phase}{suffix}.json", snapshot[key])
    (attempt / f"explain_{phase}_format_json.txt").write_text(snapshot["explain_format_json_raw"] + "\n", encoding="utf-8")


def apply_index_migration(engine):
    # Import the foundation's migration runner; do not create a second engine or schema.
    sys.path.insert(0, str(REPOSITORY / "code"))
    sys.path.insert(0, str(REPOSITORY / "scripts/hw04"))
    from db_setup import migrate
    return migrate(engine, through=3)


def run_experiment(*, engine, ownership_manifest, seed_manifest, output_root):
    revision = revision_metadata(REPOSITORY)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    attempt = output_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
    attempt.mkdir()
    status = {"format_version": 1, "status": "running", "started_at_utc": utc_now(), "ddl_attempted": False}
    write_json(attempt / "status.json", status)
    stage = "ownership"
    try:
        ownership = verify_engine_ownership(engine, ownership_manifest)
        seed_path = Path(seed_manifest)
        seed_bytes = seed_path.read_bytes()
        seed = json.loads(seed_bytes)
        title = seed.get("selective_title")
        if not isinstance(title, str) or not title:
            raise IndexExperimentError("Seed manifest must supply the exact selective listing title")
        metadata = {
            "format_version": 1, "started_at_utc": status["started_at_utc"],
            **revision, "ownership": ownership,
            "seed_manifest": str(seed_path.resolve()), "seed_manifest_sha256": hashlib.sha256(seed_bytes).hexdigest(),
            "migration": str(MIGRATION.relative_to(REPOSITORY)),
            "migration_sha256": hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),
            "query": QUERY, "parameters": {"title": title},
        }
        write_json(attempt / "configuration.json", metadata)
        stage = "preflight"
        before = capture_snapshot(engine, title)
        write_json(attempt / "preflight.json", before)
        validate_seed_identity(before, seed, ownership)
        assert_unindexed(before["indexes"], before["schema_migrations"])
        # This complete before snapshot is durable before the first DDL statement.
        save_snapshot(attempt, "before", before)
        stage = "ownership_recheck"
        if verify_engine_ownership(engine, ownership_manifest) != ownership:
            raise IndexExperimentError("Owned instance changed between capture and migration")
        stage = "migration"
        status["ddl_attempted"] = True
        write_json(attempt / "status.json", status)
        applied = apply_index_migration(engine)
        write_json(attempt / "applied_migrations.json", applied)
        stage = "after_capture"
        after = capture_snapshot(engine, title)
        save_snapshot(attempt, "after", after)
        stage = "comparison"
        validate_seed_identity(after, seed, ownership)
        comparison = compare_snapshots(before, after)
        write_json(attempt / "comparison.json", comparison)
        status.update(status="complete", completed_at_utc=utc_now())
        write_json(attempt / "status.json", status)
        return attempt
    except Exception as error:
        # SQL exception strings can disclose bound values or configuration. Keep
        # explicit guard messages, otherwise preserve only the exception class.
        message = str(error) if isinstance(error, (IndexExperimentError, OwnershipError)) else f"Index experiment failed ({type(error).__name__}); inspect local runtime configuration"
        status.update(status="failed", failed_at_utc=utc_now(), failure_stage=stage,
                      error_type=type(error).__name__, error=message,
                      recovery="Preserve this attempt. If DDL was attempted, inspect the index and migration journal for partial DDL. The additive migration can finish a missing journal entry, but a new experiment must refuse an existing index; never drop it to recreate before evidence.")
        write_json(attempt / "status.json", status)
        raise IndexExperimentError(message, attempt) from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ownership-manifest", required=True, type=Path)
    parser.add_argument("--seed-manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(REPOSITORY / "code"))
    from web_application.database import db_session_basede26
    try:
        attempt = run_experiment(engine=db_session_basede26, ownership_manifest=args.ownership_manifest,
                                 seed_manifest=args.seed_manifest, output_root=args.output_root)
        print(json.dumps({"status": "complete", "evidence": str(attempt)}))
        return 0
    except IndexExperimentError as error:
        print(json.dumps({"status": "failed", "evidence": str(error.attempt_path), "error": str(error)}), file=sys.stderr)
        return 1
    finally:
        db_session_basede26.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
