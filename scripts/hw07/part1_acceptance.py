"""Live HTTPS/MySQL/Mongo/Ollama Part 1 checks; no mocked dependencies.

Start the existing application on 8702 under its shared runtime lease. Write
public evidence only; retain private server logs and telemetry in --work-dir.
Only IDs/namespaces created by this run are eligible for cleanup.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]

from scripts.hw06.live_support import running_app
from scripts.hw06.runtime_lease import RuntimeLease
from src.hw06_shared.config import HW6Config
from src.hw06_shared.database import MongoConnection


def legacy_cookie_probe(cookie):
    """Keep the negative probe runnable even on a fresh database with no sessions."""
    label = "old MySQL cookie alone " if cookie else "synthetic legacy cookie alone "
    return label, {
        "Cookie": "s6102_session=" + (cookie or "synthetic-old-session-not-a-bearer-token")
    }


def run(args, result):
    config = HW6Config.from_env()
    config = HW6Config(**{**config.model_dump(), "source_commit": result["source_commit"]})
    result["config"] = config.public_dict()
    marker = "HW7-P1-" + uuid4().hex
    owned_sql, owned_docs, owned_managers, memory_users = set(), set(), set(), set()
    engine = create_engine(os.environ["HW4_DATABASE_URL"], hide_parameters=True)
    with engine.connect() as db:
        result["mysql_version"] = db.scalar(text("SELECT VERSION()"))
        legacy = db.execute(
            text("SELECT id,password_hash FROM users WHERE username LIKE 'legacy_%'")
        ).all()
        result["legacy_hash_fingerprints"] = {
            str(row.id): hashlib.sha256(row.password_hash.encode()).hexdigest() for row in legacy
        }
        cookie = db.scalar(text("SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1"))
        result["stored_users"] = [
            dict(row._mapping)
            for row in db.execute(
                text(
                    "SELECT username,role,(password_hash LIKE '$argon2id$%') AS argon2_hash FROM users "
                    "WHERE username IN ('s6102_reader','s6102_writer','s6102_moderator') ORDER BY username"
                )
            )
        ]
    with RuntimeLease(
        args.runtime_dir, owner="HW7-Part1", purpose="live JWT and HW6 regression"
    ) as lease:
        with (
            MongoConnection(config) as mongo,
            running_app(
                config,
                lease=lease,
                directory=args.work_dir,
                env_files=[args.env_file],
                cert=args.cert,
                key=args.key,
            ) as (client, _),
        ):
            database = mongo.database
            client.headers.pop("Authorization", None)
            client.auth = None
            cookie_label, cookie_headers = legacy_cookie_probe(cookie)
            result["historical_cookie_available"] = bool(cookie)

            def check(name, method, path, expected, *, headers=None, body=None, show=True):
                response = client.request(
                    method, path, headers=headers, **({"json": body} if body is not None else {})
                )
                data = response.json() if response.content else None
                safe_data = data
                if isinstance(data, dict) and "access_token" in data:
                    token = data["access_token"]
                    safe_data = {
                        **data,
                        "access_token": ".".join(token.split(".")[:2]) + ".[signature redacted]",
                    }
                entry = {
                    "name": name,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "method": method,
                    "path": path,
                    "expected": expected,
                    "actual": response.status_code,
                    "passed": response.status_code == expected,
                }
                if show:
                    entry["response"] = safe_data
                result["checks"].append(entry)
                print(json.dumps(entry), flush=True)
                if response.status_code != expected:
                    raise AssertionError(f"{name}: expected {expected}, got {response.status_code}")
                return data

            tokens, users = {}, {}
            for role in ("reader", "writer", "moderator"):
                username = os.environ[f"HW7_{role.upper()}_USERNAME"]
                body = check(
                    f"{role} login",
                    "POST",
                    "/auth/login",
                    200,
                    body={
                        "username": username,
                        "password": os.environ[f"HW7_{role.upper()}_PASSWORD"],
                    },
                )
                tokens[role] = {"Authorization": "Bearer " + body["access_token"]}
                users[role] = check(
                    f"{role} identity", "GET", "/auth/me", 200, headers=tokens[role]
                )["user"]
                assert users[role]["role"] == role
            check(
                "invalid login",
                "POST",
                "/auth/login",
                401,
                body={"username": os.environ["HW7_READER_USERNAME"], "password": "incorrect"},
            )
            for path in ("/auth/me", "/api/rentals", "/api/doc-rentals"):
                check("missing token " + path, "GET", path, 401)
                check(
                    "corrupted token " + path,
                    "GET",
                    path,
                    401,
                    headers={"Authorization": "Bearer corrupted.token.signature"},
                )
                check(cookie_label + path, "GET", path, 401, headers=cookie_headers)
            expired = jwt.encode(
                {
                    "sub": str(users["reader"]["id"]),
                    "iat": datetime.now(timezone.utc) - timedelta(hours=1),
                    "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
                    "iss": "s6102",
                    "aud": "s6102-rentals",
                },
                os.environ["HW7_JWT_SECRET"],
                algorithm="HS256",
            )
            check(
                "expired signed token",
                "GET",
                "/auth/me",
                401,
                headers={"Authorization": "Bearer " + expired},
            )
            sql_payload = {
                "listingTitle": marker,
                "propertyAddress": "10 Course Test Lane, San Jose, CA",
                "submitterEmail": "hw7-fixture@example.com",
                "description": marker + " owned acceptance record.",
                "propertyType": "apartment",
                "termsAccepted": True,
            }
            doc_payload = {
                "listingTitle": marker,
                "propertyType": "apartment",
                "description": marker,
                "availableFrom": "2026-11-01T00:00:00Z",
            }
            try:
                for path, payload, owned in (
                    ("/api/rentals", sql_payload, owned_sql),
                    ("/api/doc-rentals", doc_payload, owned_docs),
                ):
                    for role in tokens:
                        check(
                            role + " list " + path,
                            "GET",
                            path,
                            200,
                            headers=tokens[role],
                            show=False,
                        )
                        status = 403 if role == "reader" else 201
                        created = check(
                            role + " create " + path,
                            "POST",
                            path,
                            status,
                            headers=tokens[role],
                            body=payload,
                        )
                        if status == 201:
                            owned.add(created["id"])
                            detail = path + "/" + str(created["id"])
                            for reader_role in tokens:
                                check(
                                    reader_role + " read " + path,
                                    "GET",
                                    detail,
                                    200,
                                    headers=tokens[reader_role],
                                )
                            for write_role in tokens:
                                update = {**payload, "listingTitle": marker + " updated"}
                                if path == "/api/rentals":
                                    update["propertyAddress"] = sql_payload["propertyAddress"]
                                check(
                                    write_role + " update " + path,
                                    "PUT",
                                    detail,
                                    403 if write_role == "reader" else 200,
                                    headers=tokens[write_role],
                                    body=update,
                                )
                            for denied in ("reader", "writer"):
                                check(
                                    denied + " delete " + path,
                                    "DELETE",
                                    detail,
                                    403,
                                    headers=tokens[denied],
                                )
                            check(
                                "moderator delete " + path,
                                "DELETE",
                                detail,
                                204,
                                headers=tokens["moderator"],
                            )
                            owned.discard(created["id"])
                    for denied in ("reader", "writer"):
                        check(
                            denied + " delete-highest",
                            "DELETE",
                            "/api/rentals/highest",
                            403,
                            headers=tokens[denied],
                        )
                manager_payload = {
                    "name": marker,
                    "company": "Course test",
                    "email": marker.lower() + "@example.com",
                }
                check(
                    "reader manager create",
                    "POST",
                    "/api/property-managers",
                    403,
                    headers=tokens["reader"],
                    body=manager_payload,
                )
                manager = check(
                    "writer manager create",
                    "POST",
                    "/api/property-managers",
                    201,
                    headers=tokens["writer"],
                    body=manager_payload,
                )
                owned_managers.add(manager["id"])
                manager_path = "/api/property-managers/" + str(manager["id"])
                check(
                    "writer manager delete", "DELETE", manager_path, 403, headers=tokens["writer"]
                )
                check(
                    "moderator manager delete",
                    "DELETE",
                    manager_path,
                    204,
                    headers=tokens["moderator"],
                )
                owned_managers.discard(manager["id"])
                user_id = str(users["reader"]["id"]) + ":hw6:HW7-P1:" + marker
                memory_users.add(user_id)
                request = {
                    "user_id": user_id,
                    "session_id": marker,
                    "message": "I prefer a quiet apartment near campus. Please acknowledge briefly.",
                }
                check("chat missing token", "POST", "/api/chat", 401, body=request)
                check(
                    "cross-user memory denied",
                    "GET",
                    "/api/memory/999999",
                    403,
                    headers=tokens["reader"],
                )
                chat = check(
                    "HW6 live model chat",
                    "POST",
                    "/api/chat",
                    200,
                    body=request,
                    headers=tokens["reader"],
                )
                assert chat["reply"].strip()
                memory = check(
                    "HW6 persisted memory",
                    "GET",
                    "/api/memory/" + user_id,
                    200,
                    headers=tokens["reader"],
                )
                assert len(memory["messages"]) == 2
                assert database["messages"].count_documents({"user_id": user_id}) == 2
                check(
                    "HW6 aggregate",
                    "GET",
                    "/api/aggregate/" + user_id,
                    200,
                    headers=tokens["reader"],
                )
                check("HW6 configuration", "GET", "/api/hw06/config", 200, headers=tokens["reader"])
                if args.browser_node:
                    browser_dir = args.work_dir / "browser"
                    subprocess.run(
                        [str(args.browser_node), str(ROOT / "tests/browser_hw07_part1.cjs")],
                        cwd=ROOT,
                        env={**os.environ, "HW7_BROWSER_OUTPUT": str(browser_dir)},
                        check=True,
                    )
                    result["browser"] = json.loads((browser_dir / "browser.json").read_text())
            finally:
                for row_id in owned_sql:
                    client.delete(
                        f"/api/rentals/{row_id}", headers=tokens["moderator"]
                    ).raise_for_status()
                for row_id in owned_docs:
                    client.delete(
                        f"/api/doc-rentals/{row_id}", headers=tokens["moderator"]
                    ).raise_for_status()
                for row_id in owned_managers:
                    client.delete(
                        f"/api/property-managers/{row_id}", headers=tokens["moderator"]
                    ).raise_for_status()
                for name in ("messages", "summaries", "episodes"):
                    for user_id in memory_users:
                        database[name].delete_many({"user_id": user_id})
                result["owned_fixture_cleanup"] = True
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("env-file", "runtime-dir", "work-dir", "cert", "key", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--browser-node", type=Path)
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    result = {
        "homework": 7,
        "scope": "baseline and Part 1 only",
        "student": "Pragya Apurva",
        "sid4": 6102,
        "seed": 6102,
        "verify_seed": 266102,
        "evidence_kind": "live HTTPS with real MySQL, MongoDB and Ollama; no mocked services",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "checks": [],
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--",
                    "code",
                    "src",
                    "scripts",
                    "frontend",
                    "tests",
                    "requirements*.txt",
                    "pyproject.toml",
                    ".pre-commit-config.yaml",
                ],
                cwd=ROOT,
                text=True,
            ).strip()
        ),
    }
    try:
        run(args, result)
        result["passed"] = all(check["passed"] for check in result["checks"])
    except Exception as error:
        result.update(passed=False, error_type=type(error).__name__)
        print(
            "Live acceptance failed; inspect statuses and private server log:", type(error).__name__
        )
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Pragya Apurva | Part 1 checks={len(result['checks'])} passed={result['passed']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
