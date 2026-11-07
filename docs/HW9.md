# HW9 integrated application

Pragya Apurva · DATA 260 · SID4 6102

The assigned application runs at `http://127.0.0.1:8702`, with a cosine cutoff of
0.85 and rental-data-version enforcement enabled. The Redis counter runs on
successful authenticated SQL rental-detail reads. The semantic cache wraps
`POST /api/kafka/questions`; misses use the existing three-process HW8 pipeline.
Part 4 uses the existing local model adapter directly, bypassing the cache.

## One setup path

Use Python 3.12, Node.js 22.12+, Docker Compose with `!override` support, and
Ollama. Keep a private runtime directory outside the repository. Run these
commands from the repository root. Choose unused service ports and an owned
database instance; the example uses MySQL 3399, Kafka 19099, and Redis 6399.

Create `$HW9_RUNTIME/private.env` privately with:

```text
MYSQL_ROOT_PASSWORD=<private database password>
HW4_DATABASE_URL=mysql+pymysql://root:<same password>@127.0.0.1:3399/s6102_rel
HW7_JWT_SECRET=<private random secret of at least 32 bytes>
HW7_JWT_TTL_SECONDS=900
HW7_READER_USERNAME=<private teaching reader>
HW7_READER_PASSWORD=<private reader password>
HW7_WRITER_USERNAME=<private teaching writer>
HW7_WRITER_PASSWORD=<private writer password>
HW7_MODERATOR_USERNAME=<private teaching moderator>
HW7_MODERATOR_PASSWORD=<private moderator password>
HW9_MYSQL_PORT=3399
HW9_KAFKA_PORT=19099
HW9_REDIS_PORT=6399
KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:19099
HW9_REDIS_URL=redis://127.0.0.1:6399/0
OLLAMA_BASE_URL=http://127.0.0.1:11434
HW9_CACHE_NAMESPACE=integration
HW9_CACHE_THRESHOLD=0.85
HW9_CACHE_DEMO_ALLOW_STALE=0
```

```bash
python3.12 -m venv "$HW9_RUNTIME/venv"
source "$HW9_RUNTIME/venv/bin/activate"
pip install -r requirements-hw09.txt
set -a
source "$HW9_RUNTIME/private.env"
set +a
export PYTHONPATH=.:code
export HW8_PRIVATE_ENV="$HW9_RUNTIME/private.env"
export HW8_SOURCE_COMMIT=$(git rev-parse HEAD)
docker compose -p s6102-hw9-integration \
  -f code/docker/hw08/docker-compose.yml \
  -f code/docker/hw09/compose.cache.yml \
  -f code/docker/hw09/compose.integration.yml \
  up -d mysql kafka kafka-init redis
```

Wait for MySQL and Kafka health checks and the topic initializer to complete.
The following single command creates the database if needed, applies the
historical HW4/HW5 schema including migration 004, applies HW7 migration 005,
then the numbered migrations through 007 (003 index, 006 counter, 007 version).
It preserves existing records and checksum-protected migration history. Run it
before starting application writes. Repeating it preserves existing accounts.

```bash
python scripts/hw09/setup.py --env-file "$HW9_RUNTIME/private.env" --seed-accounts
ollama pull qwen2.5:7b
ollama pull nomic-embed-text:v1.5
(cd frontend && npm ci && npm run build)
```

Launch each process from a shell with the same private environment. Use a fresh
stage receipt directory for a fresh broker and retain it across restarts.
Only one deployment should consume these broker groups during verification.

```bash
python scripts/hw08/planner.py --state-dir "$HW9_RUNTIME/stages" > "$HW9_RUNTIME/planner.log" 2>&1 &
python scripts/hw08/writer.py --state-dir "$HW9_RUNTIME/stages" > "$HW9_RUNTIME/writer.log" 2>&1 &
python scripts/hw08/reviewer.py --state-dir "$HW9_RUNTIME/stages" > "$HW9_RUNTIME/reviewer.log" 2>&1 &
python -m src.kafka_service.worker > "$HW9_RUNTIME/worker.log" 2>&1 &
python scripts/run_hw09_web.py > "$HW9_RUNTIME/api.log" 2>&1 &
```

The launcher enables both Kafka and HW9, uses port 8702, defaults the cutoff to
0.85, and explicitly enables version enforcement. Wait for `consumer_ready`
from each stage and `semantic_cache_ready` from the web app. The latter checks
Redis Search, migration 007, and the pinned Nomic model digest. Log in through
`POST /auth/login`, then send a bearer-authenticated
`POST /api/kafka/questions` with `{"question":"How many units are available at S6102-R-9101?"}`.
Use `reports/hw09/rental_fixtures.json` only on an owned experiment database.

## Repeatable verification

Offline verification audits the saved 200-request sweep, freezes, datasets,
source ancestry, and all 40 saved Part 4 answers without model calls:

```bash
make verify-hw09 PYTHON="$HW9_RUNTIME/venv/bin/python" \
  HW9_VERIFY_ARGS="--runtime-dir $HW9_RUNTIME/verify"
```

Add `--live` to run the integrated counter verifier, authenticate through HTTP,
check a real miss and hit, compare Kafka offsets, correlate all three real model
stages on misses and none on hits, test view-checkpoint/version separation,
mutations and rollback, and run Part 4's controlled development entry point.
This creates owned synthetic fixtures and saves them for inspection. It never
reruns or edits the held-out benchmark. Run serially without other database
writes or inference jobs.

```bash
make verify-hw09 PYTHON="$HW9_RUNTIME/venv/bin/python" \
  HW9_VERIFY_ARGS="--runtime-dir $HW9_RUNTIME/verify --live --api-log $HW9_RUNTIME/api.log --stage-log-dir $HW9_RUNTIME"
```

For the final tag check, restart the application and stage processes from the
exact `hw9` checkout, set `HW8_SOURCE_COMMIT` to that checkout's SHA, and use
`--require-ref hw9 --output $HW9_RUNTIME/tag-verification.json`. This preserves
the tagged evidence bytes. The tracked receipt names the tested code commit;
the external post-tag receipt names the final report commit. The report cannot
contain the hash of its own containing commit. `TAG_TARGET.json` in the local
upload package resolves that final hash and verifies the two PDF copies.

## Tests and measurement provenance

The integrated test environment adds jsonschema 4.26.0, numpy 2.5.4, langgraph
1.2.20, and llama-index-core 0.14.25 to the application environment. Exact resolved
versions are in `reports/hw09/raw/integration/requirements-resolved.txt`.
Run the active suite under `tests/`, avoiding historical test copies in reports:

```bash
HW7_JWT_TTL_SECONDS=900 HW9_REDIS_URL= PYTHONPATH=.:code python -m pytest -q tests \
  --ignore=tests/test_hw05_meals.py --ignore=tests/test_hw05_mcp_stdio.py
```

Use a separate Python 3.12 environment with `requirements-mcp.txt` for those two
MCP files. Their HTTPX/Starlette requirements differ from the shared web app.
The integration run passed 1,528 active tests and 56 dedicated MCP tests; 25
optional older live checks were skipped and are listed in the saved test log.
Lint and the React production build passed. The inherited test fixtures disable
the view counter; the live HW9 verifier exercises it with real Redis and MySQL.

The Part 3 table comes from `audited-threshold-summary.json` and
`audited-requests.jsonl`, measured at source `52c8ef470b124605a0fc51dd8c5821b4a5f3738b`.
The cache, embedding, Kafka generation, and Part 4 source paths are unchanged
by integration, as checked by the verifier. The frozen case file remains commit
`3511ae67588f61eeff4199aa8f4db294aca04c57`, SHA-256
`4c180dd5a8b5dbd007797225889d1cb7e0921339d0670683b225674ee76f0c26`.
Part 4's frozen implementation is `7767adc8fdc4afa8ba2157ea9ecda15f41162266`.

At cutoff 0.85, 13 of 40 questions received incorrect cached answers. This is a
measured limitation of cosine matching across listing identities, retained for
the assignment. Version enforcement prevents reuse of outdated fact versions;
it does not make semantic matches factually correct. See the report and
`reports/hw09/METRICS.md` for the two scoring corrections and cost assumptions.
