"""Exercise rental views via authenticated HTTP and inspect both live stores."""

import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session
from web_application.database import db_session_basede26 as engine
from web_application.models import Rental
from web_application.rental_views import RentalViewCounter


def login(client, role):
    response = client.post(
        "/auth/login",
        json={
            "username": os.environ[f"HW7_{role}_USERNAME"],
            "password": os.environ[f"HW7_{role}_PASSWORD"],
        },
    )
    response.raise_for_status()
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def create_listing(client, writer, label):
    response = client.post(
        "/api/rentals",
        headers=writer,
        json={
            "listingTitle": f"HW9 Counter Demo {label}",
            "propertyAddress": "6102 Example Avenue, San Jose, CA",
            "submitterEmail": "counter-demo@example.com",
            "description": "A synthetic rental listing for the Homework 9 access counter.",
            "propertyType": "apartment",
            "termsAccepted": True,
        },
    )
    assert response.status_code == 201, response.status_code
    return response.json()


def read_listing(client, reader, listing):
    response = client.get(f"/api/rentals/{listing['id']}", headers=reader)
    assert response.status_code == 200, response.status_code
    assert response.json() == listing, "The legacy rental JSON changed."
    return int(response.headers["X-View-Count"])


def key(listing_id):
    return f"s6102:views:rental:{listing_id}"


def saved_count(listing_id):
    with engine.connect() as db:
        return db.execute(
            text("SELECT view_count FROM rentals WHERE id = :id"), {"id": listing_id}
        ).scalar_one()


def verify(base_url, redis):
    with httpx.Client(base_url=base_url, timeout=10) as client:
        writer, reader = login(client, "WRITER"), login(client, "READER")
        primary = create_listing(client, writer, "A")
        secondary = create_listing(client, writer, "B")
        recovery = create_listing(client, writer, "recovery")
        primary_id, secondary_id, recovery_id = (
            row["id"] for row in (primary, secondary, recovery)
        )
        for listing_id in (primary_id, secondary_id, recovery_id):
            assert not redis.exists(key(listing_id)), f"Fresh fixture has a Redis key: {listing_id}"
            assert saved_count(listing_id) == 0

        assert client.get(f"/api/rentals/{primary_id}").status_code == 401
        listing_page = client.get("/api/rentals", headers=reader)
        assert listing_page.status_code == 200 and "X-View-Count" not in listing_page.headers
        missing_id = 2_147_483_647
        assert client.get(f"/api/rentals/{missing_id}", headers=reader).status_code == 404
        assert not redis.exists(key(primary_id), key(secondary_id), key(missing_id))
        print("Auth 401, missing 404, and collection GET left counters untouched.")
        print(f"=== Testing Counter | {primary['listingCode']} ===")

        counts, checkpoints = [], {}
        for access in range(1, 26):
            count = read_listing(client, reader, primary)
            assert count == access
            counts.append(count)
            print(f"Access #{access:02d}: Total = {count}")
            saved = saved_count(primary_id)
            assert saved == access // 10 * 10
            if access in (9, 10, 20, 25):
                checkpoints[access] = saved
                print(f"  MySQL checkpoint after #{access}: {saved}")
            if access == 12:
                assert read_listing(client, reader, secondary) == 1

        assert read_listing(client, reader, secondary) == 2
        assert (int(redis.get(key(secondary_id))), saved_count(secondary_id)) == (2, 0)
        assert redis.ttl(key(primary_id)) == -1
        print(f"Separate listing {secondary['listingCode']}: Redis=2, MySQL=0")

        # Simulate a delayed checkpoint against a higher saved value on a third fixture.
        with engine.begin() as db:
            db.execute(
                text("UPDATE rentals SET view_count = 20 WHERE id = :id"), {"id": recovery_id}
            )
        redis.set(key(recovery_id), 9)
        assert read_listing(client, reader, recovery) == 10
        assert saved_count(recovery_id) == 20
        redis.delete(key(recovery_id))
        with ThreadPoolExecutor(max_workers=8) as pool:
            resumed = sorted(pool.map(lambda _: read_listing(client, reader, recovery), range(8)))
        assert resumed == list(range(21, 29))
        assert (int(redis.get(key(recovery_id))), saved_count(recovery_id)) == (28, 20)
        print("Delayed sync at 10 preserved MySQL=20. Eight concurrent cold reads returned 21–28.")

        with Session(engine) as stale:
            assert stale.get(Rental, recovery_id).view_count == 20
            with engine.begin() as db:
                db.execute(
                    text("UPDATE rentals SET view_count = 30 WHERE id = :id"), {"id": recovery_id}
                )
            redis.delete(key(recovery_id))
            recovered = RentalViewCounter(redis).increment_rental_views(stale, recovery_id)
        assert recovered == 31
        assert (int(redis.get(key(recovery_id))), saved_count(recovery_id)) == (31, 30)
        print("An older SQL snapshot resumed from the latest checkpoint 30 and returned 31.")

        live, saved = int(redis.get(key(primary_id))), saved_count(primary_id)
        assert (live, saved) == (25, 20)
        print(f"Final {primary['listingCode']}: Redis={live}, MySQL={saved}")
        return {
            "primary_listing": primary["listingCode"],
            "secondary_listing": secondary["listingCode"],
            "recovery_listing": recovery["listingCode"],
            "missing_id": missing_id,
            "counts": counts,
            "mysql_checkpoints": checkpoints,
            "secondary_final": {"redis": 2, "mysql": 0},
            "resumed_counts": resumed,
            "recovered_from_newer_checkpoint": recovered,
            "final": {"redis": live, "mysql": saved},
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run this verifier with Python assertions enabled.")
    if not os.environ.get("HW4_DATABASE_URL"):
        parser.error("Set HW4_DATABASE_URL for an isolated MySQL instance.")
    redis = Redis.from_url(os.environ["HW9_REDIS_URL"], socket_timeout=2)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    print(f"Pragya Apurva | DATA 260 Homework 9 Part 1 | {started}")
    print(f"Source commit: {revision}")
    result = verify(args.base_url, redis)
    args.output.write_text(
        json.dumps(
            {
                "started_at_utc": started,
                "source_commit": revision,
                **result,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    redis.close()
    engine.dispose()


if __name__ == "__main__":
    main()
