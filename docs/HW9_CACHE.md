# HW9 Part 2 and Part 3.5 cache interface

## Start an isolated stack

Use Python 3.12, Docker Compose and local Ollama. Keep runtime files, snapshots,
secrets and service logs in an external directory. Use a distinct Compose
project, Kafka port, Redis port, HTTP port and MySQL instance for each concurrent
session. Schedule timed runs separately when sharing Ollama.

```bash
# From the repo root. Choose your own external, private runtime directory.
export HW9_RUNTIME=/absolute/external/hw9-runtime
python3.12 -m venv "$HW9_RUNTIME/venv"
source "$HW9_RUNTIME/venv/bin/activate"
pip install -r requirements-hw09-cache.txt

# Use a dedicated MySQL 8.4 instance with database s6102_rel.
# The private.env must set HW4_DATABASE_URL (a host URL), HW7_JWT_SECRET
# (32+ bytes), and the HW7_READER/WRITER/MODERATOR_USERNAME and _PASSWORD pairs.
set -a
source "$HW9_RUNTIME/private.env"
set +a
export PYTHONPATH=.:code
python scripts/hw05/part1/db_setup.py --create-database --migrate
python scripts/hw07/db_setup.py --env-file "$HW9_RUNTIME/private.env" --seed-accounts
python scripts/hw04/db_setup.py --migrate --through 7

export HW8_PRIVATE_ENV="$HW9_RUNTIME/private.env"
export HW9_KAFKA_PORT=19094 HW9_REDIS_PORT=6389
docker compose -p s6102-hw9-cache \
  -f code/docker/hw08/docker-compose.yml -f code/docker/hw09/compose.cache.yml \
  up -d kafka kafka-init redis

ollama pull nomic-embed-text:v1.5
ollama pull qwen2.5:7b
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export KAFKA_BOOTSTRAP_SERVERS="127.0.0.1:$HW9_KAFKA_PORT"
export HW9_REDIS_URL="redis://127.0.0.1:$HW9_REDIS_PORT/0"
export HW8_SOURCE_COMMIT="$(git rev-parse HEAD)"
```

Run the following three processes against that broker, with a fresh receipt
directory on a fresh broker. Wait for their `consumer_ready` JSON events.

```bash
for stage in planner writer reviewer; do
  python "scripts/hw08/$stage.py" --state-dir "$HW9_RUNTIME/stages" \
    > "$HW9_RUNTIME/$stage.log" 2>&1 &
done
```

Launch FastAPI with both feature flags and keep its JSON event log. Use the
same inherited environment in every terminal. Restart **only the web process**
when changing cache settings.

```bash
export HW8_KAFKA_ENABLED=1 HW9_CACHE_ENABLED=1
export HW9_CACHE_THRESHOLD=0.85 HW9_CACHE_NAMESPACE=cache-example
export HW9_CACHE_DEMO_ALLOW_STALE=0
python -m uvicorn web_application.main:app --host 127.0.0.1 --port 18702 \
  > "$HW9_RUNTIME/api-cache-example.log" 2>&1
```

The startup event `semantic_cache_ready` reports the index and exact embedding
configuration. It checks migration 007, Redis Search and the local Ollama model
digest. The embedding is Nomic `nomic-embed-text:v1.5` at digest
`0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`,
with `clustering: ` applied to every query, 768 float32 coordinates, and
Redis Search FLAT cosine distance. Redis stores entries and indexes under
`s6102:hw9:semantic:<namespace>:`. [Redis vector search](https://redis.io/docs/latest/develop/ai/search-and-query/vectors/)

## HTTP and log contract

Log in with `POST /auth/login` using the existing username and password,
then use the returned bearer token for `POST /api/kafka/questions` with
`{"question":"How many units are available at S6102-R-9101?"}`.
Use one account throughout a benchmark. The service shares reusable entries
across requests within that authenticated account.

| Response field | Meaning |
| --- | --- |
| `answer` | Final approved Reviewer answer |
| `is_cached` | Whether a qualifying entry supplied the answer |
| `similarity` | Cosine similarity of the nearest eligible entry, including below-threshold misses. Null if no eligible entry exists. |
| `latency_ms` | Server elapsed milliseconds from ingress through the answer |
| `request_id` | Fresh UUID on every successful request |

The API's `semantic_cache_result` events include `request_id`,
`matched_question`, `matched_request_id`, `matched_data_version`,
`dataset_id`, `data_version`, `version_enforced`, `pipeline_attempted`,
`cache_write` and `timings_ms`. A hit has no `question_sent`,
`final_received` or agent `model_result` for its request ID. Those
events use the same ID as `correlation_id` on a miss. The embedding
call happens for both hits and misses. Model bypass refers to the three
generative agent calls.

Explicit listing codes resolve to title, property type and available units in
the same MySQL read as the data marker. The code stays in the embedding text so
the study can detect confusion between two similar questions about different
listings. Rental creates, updates and deletes through the SQL API advance the
shared version in their write transaction. During an experiment, change fixture
facts through the SQL API and keep the database and account fixed. One mutation
makes all older answers in that dataset ineligible. A write during a model run
can leave the original caller with a response from its starting snapshot. The
cache logs `skipped_version_changed` and stores no answer for that request.

## Session C seed snapshot and sweep

1. Load the synthetic fixtures into the dedicated MySQL instance. Complete
   fixture writes before seeding. Make a JSON array of the exact seed question
   strings in `"$HW9_RUNTIME/seed-questions.json"`.
2. Start FastAPI with `HW9_CACHE_NAMESPACE=c-seed-01`,
   `HW9_CACHE_THRESHOLD=1` and stale mode off. Send each seed once using the same
   account as the sweep. Require HTTP 200, `is_cached=false`, `cache_write=stored`
   in the correlated log, and check each answer against the fixture manifest.
3. Stop that web process and export the checked entries.

   ```bash
   HW9_CACHE_NAMESPACE=c-seed-01 python -m scripts.hw09.cache_snapshot \
     export "$HW9_RUNTIME/seed.json" --questions "$HW9_RUNTIME/seed-questions.json"
   shasum -a 256 "$HW9_RUNTIME/seed.json"
   jq -r '.entries[] | [.source_request_id,.question,.answer] | @tsv' "$HW9_RUNTIME/seed.json"
   ```

4. Before each cutoff, choose an unused namespace, restore the same snapshot,
   then start the web process for that cutoff. Example for the first pass:

   ```bash
   export HW9_CACHE_NAMESPACE=c-sweep-075-01 HW9_CACHE_THRESHOLD=0.75
   export HW9_CACHE_DEMO_ALLOW_STALE=0
   python -m scripts.hw09.cache_snapshot restore "$HW9_RUNTIME/seed.json"
   python -m uvicorn web_application.main:app --host 127.0.0.1 --port 18702 \
     > "$HW9_RUNTIME/api-$HW9_CACHE_NAMESPACE.log" 2>&1
   ```

   Repeat with fresh namespaces and cutoffs 0.80, 0.85, 0.90 and 0.95. The
   restore checks dataset, version and embedding identity, preserves all seed
   vectors and request IDs, refuses a used index or namespace, and checks the
   indexed count. A rerun uses a new namespace suffix. Stop each web process
   between runs and leave fixtures untouched until the sweep is complete.

## Session C stale-before demonstration

In a separate fixture phase use `S6102-R-9199` with three available units.
Start with `HW9_CACHE_NAMESPACE=stale-demo-c-01` and
`HW9_CACHE_DEMO_ALLOW_STALE=1`. Ask the exact unit-count question, verify the
live answer of three and confirm its Redis write. Update the fixture via
authenticated `PUT /api/rentals/<numeric-id>`. Read the fixture first and
copy its current title and address into the required PUT fields:

```json
{"listingTitle":"<current title>","propertyAddress":"<current address>","availableUnits":1}
```

Repeat the question and record the old answer and both data versions. Stop the
web process and restart in the **same namespace** with
`HW9_CACHE_DEMO_ALLOW_STALE=0`. Repeat twice and capture a miss followed by a
hit, both at one. The switch can only be enabled in `stale-demo-*` namespaces.
Storage still checks the current version in both modes.

## Session B Part 2 runner

On an isolated database, launch the web process at cutoff 0.85 in a fresh
namespace after warming Ollama outside that namespace. Run the 12 measured
requests, with the environment above and the moderator credentials loaded:

```bash
python -m scripts.hw09.cache_part2 --create-fixtures \
  --output "$HW9_RUNTIME/part2.jsonl"
```

Use `--create-fixtures` once per dedicated database. A second run can reuse
those fixtures and must use another fresh cache namespace. The runner records
every attempt and includes HTTP elapsed time alongside the server timing.
