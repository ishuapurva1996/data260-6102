#!/usr/bin/env python3
"""Capture real Part 1 checks through A's shared MongoDB and integrated HTTPS API.

Run with python -m scripts.hw06.part1.verify from the repository root. No server
is launched, no authentication is bypassed, and cleanup uses only captured IDs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from http.cookiejar import MozillaCookieJar
import json
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

from bson import ObjectId
from dotenv import load_dotenv
import httpx
from pymongo.errors import OperationFailure

from scripts.hw06.runtime_lease import LeaseBusy, RuntimeLease
from src.hw06_documents.validation import RENTAL_VALIDATOR
from src.hw06_shared.config import HW6Config
from src.hw06_shared.database import MongoConnection
from src.hw06_shared.serialization import json_value, utc_now


ROOT = Path(__file__).resolve().parents[3]


class CheckFailed(RuntimeError):
    """Only fixed, public acceptance messages; never wrap private driver text."""


def source_identity():
    paths = sorted((ROOT / "src/hw06_documents").glob("*.py"))
    paths += [ROOT / "code/web_application/routers/doc_rentals.py", Path(__file__).resolve()]
    return {"commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                              text=True).strip(),
            "sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def require(condition, message):
    if not condition:
        raise CheckFailed(message)


def capture(args, result):
    config = HW6Config.from_env()
    result["config"] = config.public_dict()
    with RuntimeLease(args.runtime_dir, owner="B", purpose="Part 1 real MongoDB/API acceptance"):
        with MongoConnection(config) as connection:
            try:
                connection.ping()
                result["mongodb"] = {"reachable": True, "database": config.database_name}
            except Exception as error:
                result["mongodb"] = {"reachable": False, "database": config.database_name,
                                     "error_type": type(error).__name__}
                result["pending"] = ["A must provision/start shared MongoDB and rerun full acceptance.",
                                     "Capture actual CRUD/invalid responses and Compass or mongosh sample view."]
                return 2
            if args.probe_only:
                result["status"] = "availability_only"
                result["pending"] = ["Full integrated API and stored-validator acceptance not attempted."]
                return 0
            require(args.cookie_file is not None, "Supply --cookie-file from a real HTTPS login.")
            jar = MozillaCookieJar(str(args.cookie_file))
            jar.load(ignore_discard=True, ignore_expires=False)
            verify = str(args.ca_file) if args.ca_file else True
            with httpx.Client(base_url=args.base_url, cookies=jar, verify=verify, timeout=15,
                              follow_redirects=False, trust_env=False) as client:
                require(client.get("/api/auth/me").status_code == 200,
                        "Existing application login unavailable; refresh the private cookie file.")
                result["auth"] = "existing HTTPS login verified; cookies not recorded"
                server_config = client.get("/api/hw06/config")
                result["server_config_status"] = server_config.status_code
                require(server_config.status_code == 200, "A's integrated configuration endpoint is unavailable.")
                result["server_config"] = server_config.json()
                run_api_checks(client, connection.database, result, keep_sample=args.keep_sample)
    result["status"] = "passed"
    result["pending"] = ["Take real application/client and Compass or mongosh screenshots; show Pragya Apurva."]
    return 0


def run_api_checks(client, database, result, *, keep_sample=False):
    prefix = "/api/doc-rentals"
    marker = f"HW6-B-{uuid4().hex[:12]}"
    result["fixture_marker"] = marker
    result["responses"] = []
    collection = database["rentals"]
    owned_ids = set()
    retained_ids = set()

    def request(method, path, expected, body=None):
        started = utc_now()
        timer = time.monotonic()
        response = client.request(method, path, **({"json": body} if body is not None else {}))
        result["responses"].append({"method": method, "path": path, "request_json": body,
                                    "status_code": response.status_code,
                                    "response_json": response.json() if response.content else None,
                                    "started_at": json_value(started),
                                    "http_latency_ms": (time.monotonic() - timer) * 1000})
        require(response.status_code == expected, f"Unexpected HTTP status for {method} {path}.")
        return response.json() if response.content else None

    payload = {"listingTitle": f"  {marker} apartment  ", "propertyType": "apartment",
               "availableFrom": "2026-11-01T09:00:00-07:00", "description": marker}
    try:
        created = request("POST", prefix, 201, payload)
        oid = ObjectId(created["id"])
        owned_ids.add(oid)
        require(created["listingTitle"] == payload["listingTitle"].strip(), "Title not trimmed.")
        require(created["status"] == "available", "Default status mismatch.")
        require(created["availableFrom"] == "2026-11-01T16:00:00Z", "Date is not UTC.")
        require(created["created_at"] == created["updated_at"], "Initial timestamps differ.")
        target = f"{prefix}/{oid}"
        require(any(row["id"] == str(oid) for row in request("GET", prefix, 200)), "List omitted fixture.")
        require(request("GET", target, 200) == created, "BSON roundtrip changed the response.")
        updated = request("PUT", target, 200, {**payload, "status": "reserved", "listingTitle": marker + " condo",
                                               "propertyType": "condo"})
        require(updated["created_at"] == created["created_at"], "PUT changed created_at.")
        require(updated["updated_at"] >= created["updated_at"], "PUT timestamp moved backwards.")
        require(updated["status"] == "reserved" and updated["propertyType"] == "condo", "PUT fields differ.")
        result["stored_sample"] = json_value(collection.find_one({"_id": oid}))
        options = collection.options()
        result["collection_options"] = json_value(options)
        require(options.get("validator") == RENTAL_VALIDATOR, "Stored validator differs from source.")
        require(options.get("validationLevel") == "strict" and options.get("validationAction") == "error",
                "Stored validation must be strict/error.")
        invalid = [({k: v for k, v in payload.items() if k != field}, f"missing_{field}") for field in
                   ["listingTitle", "propertyType", "availableFrom"]]
        invalid += [({**payload, key: value}, name) for name, key, value in [
            ("blank_title", "listingTitle", " \t"), ("long_title", "listingTitle", "x" * 101),
            ("title_type", "listingTitle", 6102), ("description_type", "description", []),
            ("bad_status", "status", "pending"), ("bad_property", "propertyType", "castle"),
            ("bad_date", "availableFrom", "2026-02-30T00:00:00Z"),
            ("naive_date", "availableFrom", "2026-11-01T00:00:00"),
            ("date_type", "availableFrom", 1793520000),
            ("server_timestamp", "created_at", "2000-01-01T00:00:00Z")]]
        for body, name in invalid:
            for method, path in [("POST", prefix), ("PUT", target)]:
                request(method, path, 422, body)
                result["responses"][-1]["case"] = name
        require(request("GET", target, 200) == updated, "Invalid PUT changed the document.")
        request("GET", f"{prefix}/bad-id", 422)
        request("GET", f"{prefix}/{ObjectId()}", 404)
        verify_stored_validation(collection, owned_ids, marker, result)
        request("DELETE", target, 204)
        request("GET", target, 404)
        result["checks"] = {name: True for name in ["five_operations", "defaults", "utc_dates",
                            "server_timestamps", "created_at_preserved", "invalid_create_and_put",
                            "malformed_id", "missing_record", "stored_validation"]}
        if keep_sample:
            sample = request("POST", prefix, 201, {**payload, "listingTitle": marker + " Compass sample"})
            sample_id = ObjectId(sample["id"])
            owned_ids.add(sample_id)
            result["sample_for_capture"] = {"id": str(sample_id), "document": sample,
                                             "cleanup": f"DELETE {prefix}/{sample_id}"}
            retained_ids.add(sample_id)
    finally:
        # Includes any accidental invalid insert. Never delete by broad title/user filters.
        # If a POST response was lost, discover only this run's unguessable fixture marker.
        for row in collection.find({"description": marker}, {"_id": 1}):
            owned_ids.add(row["_id"])
        for oid in owned_ids - retained_ids:
            collection.delete_one({"_id": oid})
        result["cleanup"] = {"scope": "this run's captured ObjectIds and unique marker",
                              "count": len(owned_ids - retained_ids), "retained_ids": sorted(map(str, retained_ids))}


def verify_stored_validation(collection, owned_ids, marker, result):
    now = datetime.now(timezone.utc)
    base = {"listingTitle": marker, "description": marker, "status": "available", "propertyType": "house",
            "availableFrom": now, "created_at": now, "updated_at": now}
    cases = [({k: v for k, v in base.items() if k != key}, f"missing_{key}") for key in
             ["listingTitle", "status", "propertyType", "availableFrom", "created_at", "updated_at"]]
    cases += [({**base, key: value}, name) for name, key, value in [
        ("blank_title", "listingTitle", " \t"), ("untrimmed_title", "listingTitle", " title "),
        ("unicode_blank_title", "listingTitle", "\u00a0"), ("trailing_newline", "listingTitle", "title\n"),
        ("long_title", "listingTitle", "x" * 101), ("title_type", "listingTitle", 3),
        ("bad_status", "status", "unknown"), ("bad_property", "propertyType", "castle"),
        ("date_type", "availableFrom", "2026-11-01T00:00:00Z"), ("description_type", "description", 3),
        ("long_description", "description", "x" * 5001), ("extra_field", "extra", True)]]
    result["direct_bson_validation"] = []
    for document, name in cases:
        oid = ObjectId()
        owned_ids.add(oid)
        try:
            collection.insert_one({**document, "_id": oid})
        except OperationFailure as error:
            require(error.code == 121, "Direct BSON validation failed for a different reason.")
            result["direct_bson_validation"].append({"case": name, "rejected": True, "mongo_code": error.code})
        else:
            raise CheckFailed(f"MongoDB accepted invalid BSON case {name}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--keep-sample", action="store_true", help="Retain one new synthetic document for Compass capture")
    parser.add_argument("--base-url", default="https://localhost:8702")
    parser.add_argument("--cookie-file", type=Path, help="Private Netscape cookie jar from existing HTTPS login")
    parser.add_argument("--ca-file", type=Path, help="Local HTTPS CA/certificate; TLS verification remains enabled")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    load_dotenv(args.env_file)
    result = {"student": "Pragya Apurva", "part": 1, "started_at": json_value(utc_now()),
              "status": "blocked", "evidence_kind": "real_availability_probe" if args.probe_only else "real_integrated_api",
              "source": source_identity(), "tools": {name: shutil.which(name) for name in ["mongosh", "mongod"]}}
    try:
        exit_code = capture(args, result)
    except LeaseBusy:
        result["pending"] = ["Shared runtime lease is busy; inspect owner.json and retry after release."]
        exit_code = 2
    except CheckFailed as error:
        result["status"] = "failed"
        result["failed_check"] = str(error)
        exit_code = 1
    except Exception as error:
        # No exception string: it may contain URI/cookie/driver details.
        result["status"] = "failed"
        result["error_type"] = type(error).__name__
        result["pending"] = ["Resolve failed acceptance from saved statuses/checks, then rerun in a fresh output directory."]
        exit_code = 1
    result["finished_at"] = json_value(utc_now())
    (args.output_dir / "verification.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(f"Pragya Apurva | Part 1 | {result['status']} | {result['finished_at']}")
    print(f"Saved: {args.output_dir / 'verification.json'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
