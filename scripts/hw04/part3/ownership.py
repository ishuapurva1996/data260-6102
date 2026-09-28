"""Fail-closed ownership checks for the disposable Part 3 Docker MySQL instance.

The external JSON manifest contains no credentials. It must identify the exact
running container, loopback port, database, and live MySQL server UUID. Checking
only the database name would not distinguish this instance from sibling work.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from uuid import UUID


class OwnershipError(ValueError):
    """A target could not be proved to be the owned disposable instance."""


def validate_manifest(manifest: dict) -> dict:
    required = {
        "format_version", "purpose", "disposable", "host", "port", "database",
        "server_uuid", "docker_container_id", "docker_container_name",
    }
    if not isinstance(manifest, dict) or not required.issubset(manifest):
        raise OwnershipError("Ownership manifest is missing required identity fields")
    if manifest["format_version"] != 1 or manifest["purpose"] != "hw04-part3-performance":
        raise OwnershipError("Ownership manifest must designate this Part 3 experiment")
    if manifest["disposable"] is not True:
        raise OwnershipError("Ownership manifest must explicitly mark this instance disposable")
    if manifest["host"] not in {"127.0.0.1", "::1"}:
        raise OwnershipError("Only an explicitly loopback-bound MySQL instance is permitted")
    if type(manifest["port"]) is not int or not 1 <= manifest["port"] <= 65535:
        raise OwnershipError("Ownership manifest must contain a valid explicit host port")
    if manifest["database"] != "s6102_rel":
        raise OwnershipError("Part 3 requires the database s6102_rel")
    try:
        canonical_uuid = str(UUID(manifest["server_uuid"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise OwnershipError("A valid live MySQL server UUID is required") from exc
    if canonical_uuid != manifest["server_uuid"].lower():
        raise OwnershipError("MySQL server UUID must use canonical hyphenated formatting")
    if not isinstance(manifest["docker_container_id"], str) or not re.fullmatch(r"[0-9a-f]{64}", manifest["docker_container_id"]):
        raise OwnershipError("Ownership requires the complete Docker container ID")
    if not isinstance(manifest["docker_container_name"], str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", manifest["docker_container_name"]):
        raise OwnershipError("Ownership requires a valid Docker container name")
    return manifest


def validate_observed_target(manifest: dict, observed: dict) -> None:
    """Validate independent observations before allowing any experiment write."""
    validate_manifest(manifest)
    for field in ("host", "port", "database", "server_uuid", "docker_container_id", "docker_container_name"):
        if observed.get(field) != manifest[field]:
            raise OwnershipError(f"Owned instance identity mismatch: {field}")
    if observed.get("dialect") != "mysql" or observed.get("docker_running") is not True:
        raise OwnershipError("The owned target must be a running MySQL Docker container")
    if observed.get("docker_bind_host") != manifest["host"] or observed.get("docker_bind_port") != manifest["port"]:
        raise OwnershipError("Docker must publish MySQL 3306 at exactly the owned loopback host/port")


def read_manifest(path: str | Path) -> dict:
    resolved = Path(path).expanduser().resolve()
    repository = Path(__file__).resolve().parents[3]
    if resolved.is_relative_to(repository):
        raise OwnershipError("The ownership manifest must be supplied outside the repository")
    try:
        return validate_manifest(json.loads(resolved.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise OwnershipError("Cannot read the external ownership manifest") from exc


def verify_engine_ownership(engine, manifest_path: str | Path) -> dict:
    """Verify Docker and a read-only live identity query using the shared engine.

    This function never creates a connection stack or outputs the engine URL.
    It intentionally returns only non-secret experiment identity information.
    """
    from sqlalchemy import text

    manifest = read_manifest(manifest_path)
    url = engine.url
    if engine.dialect.name != "mysql":
        raise OwnershipError("Only real MySQL can be used for this experiment")
    for field, actual in (("host", url.host), ("port", url.port or 3306), ("database", url.database)):
        if actual != manifest[field]:
            raise OwnershipError(f"Configured engine does not match owned target: {field}")
    try:
        inspected = subprocess.run(
            ["docker", "inspect", manifest["docker_container_id"]],
            check=True, text=True, capture_output=True, timeout=15,
        )
        container = json.loads(inspected.stdout)[0]
        bindings = container["NetworkSettings"]["Ports"].get("3306/tcp") or []
        binding = next(
            b for b in bindings
            if b["HostIp"] == manifest["host"] and int(b["HostPort"]) == manifest["port"]
        )
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, IndexError, StopIteration, TypeError) as exc:
        raise OwnershipError("Cannot verify the owned Docker instance and published MySQL port") from exc
    with engine.connect() as connection:
        identity = connection.execute(text("SELECT @@server_uuid AS server_uuid, DATABASE() AS database_name")).mappings().one()
    observed = {
        "host": url.host, "port": url.port or 3306, "database": identity["database_name"],
        "server_uuid": identity["server_uuid"], "dialect": engine.dialect.name,
        "docker_container_id": container["Id"], "docker_container_name": container["Name"].lstrip("/"),
        "docker_running": container["State"]["Running"],
        "docker_bind_host": binding["HostIp"], "docker_bind_port": int(binding["HostPort"]),
    }
    validate_observed_target(manifest, observed)
    return {key: manifest[key] for key in manifest if key in {
        "format_version", "purpose", "disposable", "host", "port", "database",
        "server_uuid", "docker_container_id", "docker_container_name",
    }}
