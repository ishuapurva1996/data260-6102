"""Export reviewed live seeds or restore them into an unused HW9 namespace."""

import argparse
import base64
import json
import math
from pathlib import Path
from uuid import UUID

from web_application.database import SessionLocal
from web_application.rental_facts import rental_version

from src.hw09.semantic_cache import (
    DIMENSION,
    FIELDS,
    MODEL,
    MODEL_DIGEST,
    MODEL_INPUT_PREFIX,
    VECTOR,
    CacheSettings,
    SemanticCache,
)

FORMAT = {
    "format": 1,
    "model": MODEL,
    "model_digest": MODEL_DIGEST,
    "dimension": DIMENSION,
    "input_prefix": MODEL_INPUT_PREFIX,
}


def validate(snapshot, marker):
    if any(snapshot.get(key) != value for key, value in FORMAT.items()):
        raise ValueError("Snapshot embedding configuration does not match this application.")
    entries = snapshot["entries"]
    if not entries:
        raise ValueError("Snapshot must contain at least one approved live answer.")
    seen_requests = set()
    seen_questions = set()
    user_id = entries[0]["user_id"]
    for entry in entries:
        if set(entry) != {*FIELDS, "embedding"}:
            raise ValueError("Unexpected cache entry fields.")
        if (entry["dataset_id"], int(entry["data_version"])) != marker:
            raise ValueError("All seed entries must match the current MySQL dataset and version.")
        request_id = entry["source_request_id"]
        if str(UUID(request_id)) != request_id or request_id in seen_requests:
            raise ValueError("Seed source request IDs must be unique canonical UUIDs.")
        if not entry["question"].strip() or not entry["answer"].strip():
            raise ValueError("Blank seed question or answer.")
        if entry["question"] in seen_questions:
            raise ValueError("Seed questions must be unique.")
        if not user_id.isascii() or not user_id.isdecimal() or entry["user_id"] != user_id:
            raise ValueError("Seed entries must all belong to one authenticated account.")
        vector = VECTOR.unpack(base64.b64decode(entry["embedding"], validate=True))
        if not all(math.isfinite(value) for value in vector) or not any(vector):
            raise ValueError("Seed vector must be finite and nonzero.")
        seen_requests.add(request_id)
        seen_questions.add(entry["question"])


def export_snapshot(cache, path, marker, questions_path):
    entries = []
    for key in sorted(cache.redis.scan_iter(match=cache.entry_prefix + "*")):
        row = cache.redis.hgetall(key)
        entries.append(
            {
                **{field: row[field.encode()].decode() for field in FIELDS},
                "embedding": base64.b64encode(row[b"embedding"]).decode(),
            }
        )
    entries.sort(key=lambda entry: entry["question"])
    snapshot = {**FORMAT, "entries": entries}
    validate(snapshot, marker)
    if questions_path:
        questions = json.loads(questions_path.read_text())
        if not isinstance(questions, list) or sorted(questions) != [e["question"] for e in entries]:
            raise ValueError("Snapshot does not match the expected exact seed questions.")
    with path.open("x", encoding="utf-8") as output:
        json.dump(snapshot, output, indent=2, sort_keys=True)
        output.write("\n")
    return entries


def restore_snapshot(cache, path, marker):
    snapshot = json.loads(path.read_text())
    validate(snapshot, marker)
    if next(cache.redis.scan_iter(match=cache.entry_prefix + "*"), None) is not None:
        raise ValueError("Destination namespace already contains entries.")
    cache.create_index(fresh=True)
    entries = snapshot["entries"]
    with cache.redis.pipeline() as batch:
        for entry in entries:
            fields = {**entry, "embedding": base64.b64decode(entry["embedding"])}
            batch.hset(cache.entry_prefix + entry["source_request_id"], mapping=fields)
        batch.execute()
    count = cache.redis.execute_command("FT.SEARCH", cache.index, "*", "LIMIT", 0, 0)[0]
    if count != len(entries):
        raise RuntimeError("Restored index does not contain the expected number of entries.")
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("export", "restore"))
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--questions", type=Path, help="Export check against a JSON string array.")
    args = parser.parse_args()
    cache = SemanticCache(CacheSettings.from_env())
    try:
        with SessionLocal() as db:
            marker = rental_version(db, lock=True)
            if args.operation == "export":
                entries = export_snapshot(cache, args.snapshot, marker, args.questions)
            else:
                entries = restore_snapshot(cache, args.snapshot, marker)
        print(
            json.dumps(
                {
                    "operation": args.operation,
                    "namespace": cache.settings.namespace,
                    "entries": len(entries),
                    "user_id": entries[0]["user_id"],
                    "dataset_id": marker[0],
                    "data_version": marker[1],
                    "index": cache.index,
                },
                sort_keys=True,
            )
        )
    finally:
        cache.close()


if __name__ == "__main__":
    main()
