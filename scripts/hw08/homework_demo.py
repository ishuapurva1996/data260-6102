"""Run CREATE then GET with one caller-created correlation ID and record the results."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]

import httpx

from src.kafka_service.config import ENTITY_REQUESTS, ENTITY_RESPONSES, PORT_BASE, SID4
from src.kafka_service.kafka_rpc import KafkaRPC
from src.kafka_service.logging import event

RENTAL = {
    "listingTitle": "HW8 synthetic apartment",
    "propertyAddress": "100 Example Street, San Jose, CA",
    "submitterEmail": "hw8@example.com",
    "description": "Synthetic rental listing for the Kafka homework demonstration.",
    "propertyType": "apartment",
    "termsAccepted": True,
}


async def demonstrate(send, *, correlation_id=None, run_id=None):
    correlation_id = correlation_id or str(uuid4())
    run_id = run_id or f"part1-{uuid4().hex[:12]}"
    records = []
    for operation, data in (("CREATE_RENTAL", RENTAL), ("GET_RENTAL", None)):
        if operation == "GET_RENTAL":
            data = {"rental_id": records[0]["response"]["rental_id"]}
        request = {
            "correlation_id": correlation_id,
            "reply_to": ENTITY_RESPONSES,
            "operation": operation,
            "data": data,
        }
        event(
            "demo_request",
            run_id=run_id,
            correlation_id=correlation_id,
            operation=operation,
            topic=ENTITY_REQUESTS,
            message=request,
        )
        response = await send(request)
        event(
            "demo_response",
            run_id=run_id,
            correlation_id=correlation_id,
            operation=operation,
            response=response,
        )
        assert response["success"] is True, response
        assert response["correlation_id"] == correlation_id, response
        assert response["operation"] == operation, response
        records.append({"request": request, "response": response})
        if operation == "CREATE_RENTAL":
            assert UUID(response["rental_id"]).version == 4
        else:
            rental = response["rental"]
            assert rental["rental_id"] == records[0]["response"]["rental_id"]
            assert all(rental[field] == value for field, value in RENTAL.items())
    result = {
        "run_id": run_id,
        "sid4": SID4,
        "correlation_id": correlation_id,
        "passed": True,
        "exchanges": records,
    }
    event(
        "demo_complete",
        run_id=run_id,
        correlation_id=correlation_id,
        rental=records[-1]["response"]["rental"],
        passed=True,
    )
    return result


async def run(args):
    event(
        "demo_started",
        base_url=args.base_url,
        sid4=SID4,
        transport="direct Kafka" if args.direct_kafka else "FastAPI",
    )
    if args.direct_kafka:
        rpc = KafkaRPC()
        await rpc.start()
        try:
            result = await demonstrate(rpc.make_request, run_id=args.run_id)
        finally:
            await rpc.stop()
    else:
        async with httpx.AsyncClient(base_url=args.base_url, timeout=30) as client:
            token = os.getenv("HW8_TOKEN")
            if not token:
                username, password = os.getenv("HW8_USERNAME"), os.getenv("HW8_PASSWORD")
                if not username or not password:
                    raise SystemExit(
                        "Set HW8_TOKEN or HW8_USERNAME/HW8_PASSWORD for the authenticated API"
                    )
                login = await client.post(
                    "/auth/login", json={"username": username, "password": password}
                )
                login.raise_for_status()
                token = login.json()["access_token"]

            async def send(payload):
                response = await client.post(
                    "/api/kafka/rentals", json=payload, headers={"Authorization": f"Bearer {token}"}
                )
                response.raise_for_status()
                return response.json()

            result = await demonstrate(send, run_id=args.run_id)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=f"http://127.0.0.1:{PORT_BASE}")
    parser.add_argument("--direct-kafka", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
