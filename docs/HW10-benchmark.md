# HW10 trace examples and latency benchmark

## Isolated runtime

Use the [HW9 setup](HW9.md) in the benchmark worktree after verifying the A1,
A2, and B1 receipts. Check that B1 descends from A2 and A2 descends from A1.
Merge the exact B1 commit with its history intact. Start the stack only in D's
exclusive runtime window. Set `HW8_SOURCE_COMMIT` to the clean checkout's
`git rev-parse HEAD` before starting the API and agents.

Use a dedicated Compose project such as `s6102-hw10-benchmark`, unused backing
service ports, and separate MySQL, Kafka, and Redis volumes. Keep the API on
`127.0.0.1:8702` and the assigned Kafka topics on the dedicated broker. Use
an owned rental database and a fresh stage receipt directory. Keep credentials,
service logs, and per-attempt evidence under
`~/code/agent_outputs/data260-hw10-planning/session-d/`. Write the API and
agent startup logs as `api.log`, `planner.log`, `writer.log`, and
`reviewer.log` in one directory. Use the pinned generator and B1 judge settings.
Keep other inference, fixture writes, and heavy builds off the host during timing.

Set `HW9_REDIS_URL` explicitly. Use a new `HW9_CACHE_NAMESPACE=hw10-benchmark-<run-id>`
for each run, `HW9_CACHE_THRESHOLD=0.85`, and `HW9_CACHE_DEMO_ALLOW_STALE=0`.
The API creates the index at startup. Before each serial request the driver
checks the namespace is empty. If the preceding request wrote an entry, the
driver deletes that exact hash outside the timed interval and verifies that
both the namespace keys and its index are empty. The index stays live, and the
request still performs embedding, MySQL version lookup, and Redis KNN search
with the normal cache configuration. Use a fresh namespace after an interrupted
run or a standalone pilot.

## Fixture workload

Load the ten approved synthetic listings from
[`reports/hw09/rental_fixtures.json`](../reports/hw09/rental_fixtures.json)
into the owned database before warming the stack. The following command seeds
an empty database through the authenticated API. Run it with the private
runtime environment already loaded.

```bash
python - <<'PY'
import httpx
from scripts.hw09.cache_part2 import login
from scripts.hw10.collect_drafts import seed_fixtures

with httpx.Client(base_url="http://127.0.0.1:8702", timeout=15, trust_env=False) as client:
    login(client)
    existing = client.get("/api/rentals")
    existing.raise_for_status()
    if existing.json():
        raise SystemExit("Fixture seeding requires an empty owned database.")
    seed_fixtures(client)
PY
```

The driver verifies each listing's title, type, and available units. It asks
five factual questions per listing using those fields. It cycles through the
same workload to replace exclusions, using a distinct attempt ID for each
request. Cache state, rather than changes to wording, determines eligibility
for reuse. The actual cache span and API response establish each measured miss.

## Pilot and measured run

Run the command with `--pilot-only` first and check `pilot_timing.json` for all
six components. Use the pilot to budget the full run. Start the measured run
with a fresh namespace and use its first complete request as an excluded
warm-up. The runner invokes A's exporter as soon as the HTTP call returns and
B's evaluator as soon as the linked messages are available. It finishes
evaluation before sending the next request.

Keep the host awake for the run. On macOS, wrap the command in `caffeinate -is`.
The timing validator rejects spans with more than 100 ms difference between
UTC elapsed time and the recorded duration. If a request times out, check its
agent logs for late inference and exclude any overlapping attempt.

```bash
python -m scripts.hw10.benchmark \
  --a1 "$A1_SHA" --b1 "$B1_SHA" --exclusive-runtime \
  --judge-model "$JUDGE_MODEL" --judge-digest "$JUDGE_DIGEST" \
  --evaluator-python "$HW10_EVAL_RUNTIME/venv/bin/python" \
  --log-dir "$D_LOG_DIR" --output "$D_RUNTIME/measure-01"
```

The default attempt budget is 75 after the warm-up. A complete run has 50
admitted rows. A row requires an HTTP 200 response with `is_cached=false`,
matching completed API and cache miss spans, all three agent spans and four
matched Kafka handoffs, and B's successful linked evaluation. Duplicate exports
of identical spans count once. Ambiguous paths with multiple distinct spans
for a required stage go in `exclusions.jsonl`, along with hits, failures,
incomplete attempts, and the warm-up. Keep the per-attempt export and evaluator
logs in the private run directory.

Queue wait is measured from enqueue to consumer receipt at the matched topic,
partition, and offset. The producer acknowledgement supplies publication
evidence and can occur after receipt. The runner sums the four waits per trace
before computing p50 and p95. It uses linear interpolation for percentiles and
divides the sum for each stage by the sum of ingress-to-evaluation durations.
The API ingress-to-response span, response's latency field, and client HTTP
round trip are recorded separately. Setup, fact retrieval, cache write, and
handoff overhead can account for time outside the six rows.

## Example traces and evidence

Use a separate example namespace. Prime it with a known fixture question and
repeat the exact question with the same account for the hit. Capture a
successful evaluated miss and run A's controlled Writer failure on the owned
stack. Capture the failure trace via the response's `X-Trace-ID` and preserve
the Writer error. Restore the healthy Writer and verify recovery before
benchmarking. `example_summary` in `benchmark_timing.py` checks the three
captured receipts and their spans for `examples.json`.

After a complete run, curate the following files under
`reports/hw10/raw/benchmark/`.

- `spans.jsonl` contains the 50 admitted traces and the three separately
  captured examples, one copy of each span.
- `examples.json` exposes the trace IDs under `hit`, `miss`, and `failure`.
  Its `details` includes the Writer error and dead-letter location.
- `latency_rows.csv` contains one row per admitted request.
- `latency_summary.json` contains the six aggregates, separate API and full
  trace distributions, exclusions count, cache and model settings, and source SHAs.
- `attempts.jsonl` and `exclusions.jsonl` support checking admission against
  actual HTTP outcomes and recording reasons for skipped attempts.

Use the largest measured share in the complete summary to identify the first
stage to optimize. Preserve the same workload and compare against a subsequent
run before claiming a speedup.

## Offline checks

```bash
python -m pytest -q tests/test_hw10_benchmark.py
ruff check scripts/hw10/benchmark.py scripts/hw10/benchmark_timing.py tests/test_hw10_benchmark.py
```

The checks use synthetic spans, a mock HTTP transport, and a stubbed evaluator
command. They require no Kafka, Redis, MySQL, or Ollama service.
