# Run and verify DATA 260 Homework 10

The local submission is tagged `hw10`. [The report](report.pdf) uses the
runtime code revision recorded by the live smoke, and
[the verification receipt](verification.json) ties it to the five milestone
commits. The tagged checkout adds the combined verifier and report package
to that runtime code.

## 1. Set up one local stack

From a checkout of the tag, use Python 3.12, Docker Compose with `!override`
support, and Ollama. Use a fresh, owned Compose project, database, Kafka
broker, and Redis namespace. The assigned API port is 8702. The commands
assume unused loopback backing ports 3398, 19098, 6398, and 11434.

Set `HW10_RUNTIME` to an absolute private directory outside the checkout.
Create it with owner-only permissions. Create a mode-600 `private.env` there
with the following settings. Replace the angle-bracket values locally with
separate private passwords and a random JWT secret of at least 32 bytes.
Use shell-safe hex values for the passwords. Account names use lowercase
letters, digits and underscores.

```text
MYSQL_ROOT_PASSWORD=<database password>
HW4_DATABASE_URL=mysql+pymysql://root:<same password>@127.0.0.1:3398/s6102_rel
HW7_JWT_SECRET=<random JWT secret>
HW7_JWT_TTL_SECONDS=900
HW7_READER_USERNAME=hw10_reader
HW7_READER_PASSWORD=<reader password>
HW7_WRITER_USERNAME=hw10_writer
HW7_WRITER_PASSWORD=<writer password>
HW7_MODERATOR_USERNAME=hw10_moderator
HW7_MODERATOR_PASSWORD=<moderator password>
HW9_MYSQL_PORT=3398
HW9_KAFKA_PORT=19098
HW9_REDIS_PORT=6398
KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:19098
HW9_REDIS_URL=redis://127.0.0.1:6398/0
HW9_CACHE_NAMESPACE=hw10-review
HW9_CACHE_THRESHOLD=0.85
HW9_CACHE_DEMO_ALLOW_STALE=0
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Use three environments so the web app, judge, and dashboard each use their
own dependencies. The smoke uses the API directly. For the optional
semester React UI, follow the frontend build command in
[the HW9 guide](../../docs/HW9.md).

```bash
python3.12 -m venv "$HW10_RUNTIME/app"
python3.12 -m venv "$HW10_RUNTIME/judge"
python3.12 -m venv "$HW10_RUNTIME/dashboard"
APP="$HW10_RUNTIME/app/bin/python"
JUDGE="$HW10_RUNTIME/judge/bin/python"
DASH="$HW10_RUNTIME/dashboard/bin/python"
"$APP" -m pip install -r requirements-hw09.txt
"$JUDGE" -m pip install -r requirements-hw10-evaluation.txt
"$DASH" -m pip install -r requirements-hw10-dashboard.txt

set -a
source "$HW10_RUNTIME/private.env"
set +a
export PYTHONPATH=.:code
export HW8_PRIVATE_ENV="$HW10_RUNTIME/private.env"
export HW8_SOURCE_COMMIT="$(git rev-parse HEAD)"
export DEEPEVAL_TELEMETRY_OPT_OUT=YES
JUDGE_DIGEST=845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e

compose=(docker compose -p s6102-hw10-review
  -f code/docker/hw08/docker-compose.yml
  -f code/docker/hw09/compose.cache.yml
  -f code/docker/hw09/compose.integration.yml)
"${compose[@]}" up -d --wait mysql kafka redis
"${compose[@]}" up -d kafka-init
"${compose[@]}" wait kafka-init
"$APP" scripts/hw09/setup.py --env-file "$HW10_RUNTIME/private.env" --seed-accounts
```

Start `ollama serve` on loopback if it is down, then run
`ollama pull qwen2.5:7b` and `ollama pull nomic-embed-text:v1.5` if the
models are absent. Check the digests against
[the recorded settings](raw/benchmark/latency_summary.json). The cache
checks the Nomic digest and the evaluator requires the Qwen digest shown
above. Record the actual digests if reproducing with different weights.

Launch the five processes in the same shell with the environment above.
Use a fresh `stages` directory for a fresh broker and retain it across
process restarts. Keep these PID variables for cleanup.

```bash
"$APP" scripts/hw08/planner.py --state-dir "$HW10_RUNTIME/stages" > "$HW10_RUNTIME/planner.log" 2>&1 &
planner_pid=$!
"$APP" scripts/hw08/writer.py --state-dir "$HW10_RUNTIME/stages" > "$HW10_RUNTIME/writer.log" 2>&1 &
writer_pid=$!
"$APP" scripts/hw08/reviewer.py --state-dir "$HW10_RUNTIME/stages" > "$HW10_RUNTIME/reviewer.log" 2>&1 &
reviewer_pid=$!
"$APP" -m src.kafka_service.worker > "$HW10_RUNTIME/worker.log" 2>&1 &
worker_pid=$!
"$APP" scripts/run_hw09_web.py > "$HW10_RUNTIME/api.log" 2>&1 &
api_pid=$!
```

Wait for `consumer_ready` in the Planner, Writer and Reviewer logs and
`semantic_cache_ready` in the API log.

## 2. Run the live smoke and combined verifier

The collector seeds ten synthetic rental fixtures and clears entries only
in the explicitly owned cache namespace. It sends an authenticated question,
checks the miss and three generated stages, then checks the exact-repeat hit.
Run in the same shell after the processes are ready. Use a new output
directory for each smoke run.

```bash
SMOKE="$(mktemp -d "$HW10_RUNTIME/smoke.XXXXXXXX")"
"$APP" -m scripts.hw10.collect_drafts smoke --seed-fixtures \
  --log-dir "$HW10_RUNTIME" --output-dir "$SMOKE" \
  --owned-cache-namespace "$HW9_CACHE_NAMESPACE"
miss=$("$APP" -c 'import json,sys; print(json.load(open(sys.argv[1]))["miss"]["request_id"])' "$SMOKE/smoke.json")
hit=$("$APP" -c 'import json,sys; print(json.load(open(sys.argv[1]))["hit"]["request_id"])' "$SMOKE/smoke.json")
"$APP" -m scripts.hw10.export_traces --log-dir "$HW10_RUNTIME" \
  --trace-id "$miss" --trace-id "$hit" --output-dir "$SMOKE/tracing"
"$JUDGE" -m scripts.hw10.evaluate pipeline --evidence-root "$SMOKE" \
  --trace-id "$miss" --model-digest "$JUDGE_DIGEST"
"$DASH" -m scripts.hw10.verify --smoke-evidence "$SMOKE" \
  --output "$SMOKE/verification.json"
```

The verifier checks Git ancestry and both A2 blobs, recalculates all judge
statistics and latency aggregates from the raw records, verifies all 50
misses and matched handoffs, opens all three examples with Streamlit AppTest,
and checks that the live smoke came from the current checkout. For an offline
audit, omit `--smoke-evidence`. The tracked smoke evidence and receipt
record their own runtime code SHA.

View the recorded dashboard in a second shell. It uses the saved evidence
and can run independently of the API, broker, cache and judge.

```bash
HW10_EVIDENCE_ROOT="$PWD/reports/hw10/raw" "$HW10_RUNTIME/dashboard/bin/python" \
  -m streamlit run scripts/hw10/dashboard.py --server.address 127.0.0.1 \
  --server.port 8511 --server.headless true
```

Open `http://127.0.0.1:8511`. Use the three buttons on Trace Lookup
or paste the IDs listed in [the dashboard receipt](DASHBOARD_VERIFICATION.md).

## 3. Reproduce the original measurements

Use the same app and judge environments with
[the evaluation runbook](../../docs/HW10-evaluation.md) and
[the latency runbook](../../docs/HW10-benchmark.md). The latter documents
the controlled Writer failure, recovery, pilot, and 50-miss experiment.
The benchmark driver takes `--evaluator-python "$JUDGE"`. Use separate
owned namespaces for examples, pilot and measured runs, an awake host,
and fresh external output directories. The milestone inputs, digests, run
settings and source commits are recorded in the
[evaluation evidence notes](raw/evaluation/README.md) and
[benchmark evidence notes](raw/benchmark/README.md).

To clean up, stop Streamlit with Ctrl-C. In the stack shell, run
`kill "$api_pid" "$worker_pid" "$reviewer_pid" "$writer_pid" "$planner_pid"`
and `"${compose[@]}" down`. Stop Ollama if you started it for this run.
