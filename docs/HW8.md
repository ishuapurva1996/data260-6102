# HW8: Kafka rental requests and three separate agents

The existing semester FastAPI factory gains `POST /api/kafka/rentals` when
`HW8_KAFKA_ENABLED=1`. Authentication continues to use the existing MySQL JWT
accounts. CREATE requires writer/moderator; GET accepts any authenticated role.
The entity worker stores UUID rentals and replay responses in Python dictionaries.
Those dictionaries disappear on worker restart. Existing SQL/Mongo routes keep
their existing behavior.

## Local setup

Use Python 3.12 and an external runtime directory. Install `requirements-hw08.lock.txt`
into a virtual environment there. Keep a private env file outside the repository:

```text
HW4_DATABASE_URL=mysql+pymysql://USER:PASSWORD@host.docker.internal:3309/s6102_rel
HW7_JWT_SECRET=YOUR_EXISTING_PRIVATE_SECRET_AT_LEAST_32_BYTES
HW7_JWT_TTL_SECONDS=900
```

The database must already have the semester schema and accounts. This stack does
not recreate or reseed the database. Set `HW8_PRIVATE_ENV` to that file, make port
8702 available, and start the stack from the repository root:

```bash
export HW8_SOURCE_COMMIT=$(git rev-parse HEAD)
docker compose -f code/docker/hw08/docker-compose.yml up -d --build
export PYTHONPATH=.:code
python scripts/hw08/homework_demo.py --output reports/hw08/raw/part1/roundtrip_http.json
```

For HTTP demo login set `HW8_USERNAME` and `HW8_PASSWORD` privately, or provide
`HW8_TOKEN`. The demo never prints the token. `--direct-kafka` tests the same worker
without the HTTP wrapper. Host clients use `127.0.0.1:9092`; containers use
`kafka:19092`. Kafka is a single KRaft broker, replication factor 1.

Seven explicit application topics use prefix `s6102`. `tasks` has two partitions;
`entity_requests`, `entity_responses`, `inbox`, `drafts`, `final`, and `dead_letter`
each have one. Initialization fails if an existing topic has a different count.

## Separate agent processes

Run each line in a separate terminal; use the same external state directory:

```bash
python scripts/hw08/planner.py --state-dir "$HW8_RUNTIME/stages"
python scripts/hw08/writer.py --state-dir "$HW8_RUNTIME/stages"
python scripts/hw08/reviewer.py --state-dir "$HW8_RUNTIME/stages"
python scripts/hw08/send_question.py --output reports/hw08/raw/part2/final.json
```

Default model is local `qwen2.5:7b`, using `src/model_client.py`. `OLLAMA_BASE_URL`
can override the local endpoint. Outputs use temperature 0, seed 6102, context
4096 and at most 256 generated tokens per stage. Agents pass work only through
Kafka. Separate stage SQLite files store local receipts; they are not handoffs.
Two Writers share `writer.sqlite3`, the same consumer group and distinct instances.
Do not share receipt files across independent deployments with unrelated offsets.

## Reliability and experiments

Normal mode commits a partition's next offset only after the output or dead-letter
publication is acknowledged. Completed output is retained before publication. A
crash can cause replay between publication and its local published flag; downstream
receipts suppress the repeated logical result. This is at-least-once transport,
not a distributed exactly-once transaction. Retry state persists three total
attempts per source record. Keep the state directory intact across restart.

The explicit `--baseline early-commit|no-retry|no-dedup` options reproduce defects
for the report; they are never defaults. `--model fixture` provides deterministic
prose for transport experiments and is logged as a test double.

Stop all pipeline processes before running the coordinator harness. It primes new
groups to topic ends to isolate experiments, and retains groups during restart:

```bash
python scripts/hw08/failure_experiments.py --runtime-dir "$HW8_RUNTIME/failures" \
  --output-dir reports/hw08/raw/part3
```

For entity duplicates, stop only the Compose worker, run the harness, then restart it:

```bash
docker compose -f code/docker/hw08/docker-compose.yml stop worker
python scripts/hw08/entity_duplicate_experiment.py --runtime-dir "$HW8_RUNTIME/entity-duplicates" \
  --output-dir reports/hw08/raw/part3
docker compose -f code/docker/hw08/docker-compose.yml up -d worker
```

Ordering uses VERIFY_SEED 266102 and 20 related messages. The unkeyed baseline
explicitly alternates partitions to make distribution controlled. The corrected
run uses `key=rental_id.encode()` with no explicit partition. Draft-topic offsets
provide actual global observation order; task offsets from separate partitions
are never compared as a global clock.

## Verification

With Kafka, worker and FastAPI running, and independent pipeline processes stopped,
run from a checkout at the `hw8` tag when using `--require-ref hw8`:

```bash
python scripts/verify_hw08.py --runtime-dir "$HW8_RUNTIME/verify" --require-ref hw8
```

The full verifier needs privately configured `HW8_READER_USERNAME` / `HW8_READER_PASSWORD`,
`HW8_WRITER_USERNAME` / `HW8_WRITER_PASSWORD`, and `HW8_MODERATOR_USERNAME` /
`HW8_MODERATOR_PASSWORD`. Writer credentials also accept the demo
`HW8_USERNAME` / `HW8_PASSWORD` names. Tokens and account credentials are never emitted.

The verifier starts its own three separate stage processes, checks live topic
metadata, CREATE/GET, replay, clean errors, authenticated HTTP, and machine-readable
failure evidence. It writes `reports/hw08/verification.json`. Use a fresh external
runtime directory per verification. `--skip-http`, `--skip-pipeline`, and
`--skip-artifacts` intentionally narrow the checks; they do not prove omitted work.
Keep a post-tag receipt outside the checkout if preserving a clean tagged state.
The script changes evidence files, never application code.

`reports/hw08/` contains the report, raw evidence, metrics and AI-use disclosure.

For a complete post-tag check without changing tracked evidence, first copy the
recorded failure data into an external evidence directory, then use all three
output/runtime options:

```bash
mkdir -p "$HW8_RUNTIME/tag-evidence/raw"
cp -R reports/hw08/raw/part3 "$HW8_RUNTIME/tag-evidence/raw/part3"
python scripts/verify_hw08.py --require-ref hw8 \
  --runtime-dir "$HW8_RUNTIME/tag-runtime" \
  --evidence-dir "$HW8_RUNTIME/tag-evidence" \
  --output "$HW8_RUNTIME/tag-verification.json"
```

The current `reports/hw08/verification.json` records a full smoke test at the final
`hw8` snapshot. `SUBMISSION.json` resolves the tag and identifies the report.
Screenshot runs retain their original source commit; the application files are
identical. The publication branch may add post-tag receipts and resolve the tag
hash on the report's first page. Those reporting updates do not change application
code. The tag already includes the approved 23-page report and capture assets.
