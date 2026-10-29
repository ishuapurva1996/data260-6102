"""Live HTTP/JWT/role acceptance; credentials and bearer tokens are never emitted."""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]
import httpx

from scripts.hw08.homework_demo import RENTAL, demonstrate
from src.kafka_service.config import ENTITY_RESPONSES
from src.kafka_service.logging import event


def request(operation, data, identity=None):
    return {
        "correlation_id": identity or str(uuid4()),
        "reply_to": ENTITY_RESPONSES,
        "operation": operation,
        "data": data,
    }


async def accept_http(base_url, evidence_dir):
    checks = []

    def record(name, passed, **detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        health = await client.get("/api/health")
        health.raise_for_status()
        tokens, statuses = {}, {}
        for role in ("reader", "writer", "moderator"):
            username = os.getenv(f"HW8_{role.upper()}_USERNAME")
            password = os.getenv(f"HW8_{role.upper()}_PASSWORD")
            if role == "writer":
                username = username or os.getenv("HW8_USERNAME")
                password = password or os.getenv("HW8_PASSWORD")
            if not username or not password:
                raise ValueError("Configure private HW8 credentials for all three roles")
            response = await client.post(
                "/auth/login", json={"username": username, "password": password}
            )
            statuses[role] = response.status_code
            response.raise_for_status()
            tokens[role] = response.json()["access_token"]
            me = await client.get("/auth/me", headers={"Authorization": "Bearer " + tokens[role]})
            me.raise_for_status()
            assert me.json()["user"]["role"] == role
        record("http_role_logins", all(x == 200 for x in statuses.values()), statuses=statuses)

        denied = []
        for operation in ("CREATE_RENTAL", "GET_RENTAL"):
            response = await client.post("/api/kafka/rentals", json=request(operation, {}))
            denied.append(response.status_code)
        bad_token = await client.post(
            "/api/kafka/rentals",
            json=request("GET_RENTAL", {}),
            headers={"Authorization": "Bearer invalid.jwt.value"},
        )
        denied.append(bad_token.status_code)
        record("http_missing_invalid_token", denied == [401, 401, 401], statuses=denied)
        wrong = await client.post(
            "/auth/login",
            json={
                "username": os.getenv("HW8_WRITER_USERNAME") or os.getenv("HW8_USERNAME"),
                "password": "deliberately-wrong-hw8-test-password",
            },
        )
        record("http_wrong_password", wrong.status_code == 401, status=wrong.status_code)

        async def send(payload):
            response = await client.post(
                "/api/kafka/rentals",
                json=payload,
                headers={"Authorization": "Bearer " + tokens["writer"]},
            )
            response.raise_for_status()
            return response.json()

        roundtrip = await demonstrate(send)
        rental_id = roundtrip["exchanges"][0]["response"]["rental_id"]
        record(
            "authenticated_fastapi_wrapper",
            roundtrip["passed"],
            correlation_id=roundtrip["correlation_id"],
            rental_id=rental_id,
            create_status=200,
            get_status=200,
        )

        reader_headers = {"Authorization": "Bearer " + tokens["reader"]}
        reader_create = await client.post(
            "/api/kafka/rentals", json=request("CREATE_RENTAL", RENTAL), headers=reader_headers
        )
        reader_request = request("GET_RENTAL", {"rental_id": rental_id})
        reader_get = await client.post(
            "/api/kafka/rentals", json=reader_request, headers=reader_headers
        )
        body = reader_get.json()
        record(
            "http_reader_permissions",
            reader_create.status_code == 403
            and reader_get.status_code == 200
            and body.get("success") is True
            and body.get("rental", {}).get("rental_id") == rental_id
            and body.get("correlation_id") == reader_request["correlation_id"],
            create_status=reader_create.status_code,
            get_status=reader_get.status_code,
        )

        moderator_headers = {"Authorization": "Bearer " + tokens["moderator"]}
        moderator_create = await client.post(
            "/api/kafka/rentals", json=request("CREATE_RENTAL", RENTAL), headers=moderator_headers
        )
        moderator_body = moderator_create.json()
        moderator_request = request("GET_RENTAL", {"rental_id": moderator_body.get("rental_id")})
        moderator_get = await client.post(
            "/api/kafka/rentals", json=moderator_request, headers=moderator_headers
        )
        body = moderator_get.json()
        record(
            "http_moderator_permissions",
            moderator_create.status_code == moderator_get.status_code == 200
            and moderator_body.get("success") is True
            and body.get("success") is True
            and all(body.get("rental", {}).get(k) == value for k, value in RENTAL.items()),
            create_status=moderator_create.status_code,
            get_status=moderator_get.status_code,
        )

    output = evidence_dir / "raw/part1"
    output.mkdir(parents=True, exist_ok=True)
    (output / "roundtrip_http.json").write_text(json.dumps(roundtrip, indent=2) + "\n")
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_commit": os.getenv("HW8_SOURCE_COMMIT"),
        "base_url": base_url,
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
    }
    (output / "http_auth.json").write_text(json.dumps(result, indent=2) + "\n")
    event("http_acceptance_complete", **result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8702")
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "reports/hw08")
    args = parser.parse_args()
    result = asyncio.run(accept_http(args.base_url, args.evidence_dir))
    raise SystemExit(0 if result["passed"] else 1)
