# HW10 trace export

Run the isolated stack in [the HW9 startup guide](../../../../docs/HW9.md) from
the HW10 checkout. Use your own Compose project and service ports, an owned
database, an `hw10-*` Redis namespace, and an external directory for logs
and stage receipts. Set `HW8_SOURCE_COMMIT` to the checkout SHA before starting
the API and agents. The API uses port 8702. The baseline uses Redis cutoff
0.85, data-version enforcement, and the local `qwen2.5:7b` pipeline model.

## Export selected requests

`request_id` in the successful API body, `X-Trace-ID` on the HTTP response,
Kafka `correlation_id`, and the span's `trace_id` refer to the same request.
The trace header is also available on handled HTTP errors. To export a trace
and, for a completed miss, its linked evaluation input, run from the repository
root using the HW9 Python environment:

```bash
PYTHONPATH=.:code python -m scripts.hw10.export_traces \
  --log-dir "$HW10_RUNTIME" --output-dir "$HW10_EXPORT" \
  --trace-id "$TRACE_ID" --case-id "$CASE_ID"
```

The exporter reads the flushed `*.log` files in the external runtime
directory and writes `spans.jsonl` and `linked_cases.jsonl`. It overwrites
those two files in the chosen output directory. Omit `--case-id` to select
multiple traces with repeated `--trace-id`. For each successful miss, the
export starts at the final record received by the API and follows the Kafka
topic, partition, and offset back to the exact Writer draft, Planner plan,
and inbox message. Each entry under `messages` includes the original
`payload` and its broker and timing metadata. `reference_facts` is the
unmodified MySQL snapshot sent to the agents.

`api_request`, `cache_lookup`, and agent spans use monotonic durations.
Each agent processing attempt has its own span, with the input record
location, attempt number, model, and error if the attempt failed. API
`request_outcome` is separate from `cache_outcome`. A failed cache lookup
has a null outcome. An exact repeat receives a new trace ID and the cache
span records the original miss in `source_request_id`.

For queue time, use `operation="queue_wait"` on `inbox`, `tasks`,
`drafts`, and `final`. The enqueue time is captured just before the producer
send and carried in a Kafka header. The consumer records receipt time before
decoding. The exporter adds the independently logged producer acknowledgement
time after matching topic, partition, offset, and enqueue time. For a
completed miss, sum the four intervals identified by the broker coordinates
and receipt times in `messages`. All processes in the live run use the same
host clock. A reversed clock yields an error span with a null duration.
Headerless historical records still process normally. Their queue latency is
unavailable. Publish failures have `operation="publish"` and error status.

## Reproduce the smoke and draft collection

With the same private environment as the live services, use the smoke
command below on an owned stack. It loads the HW9 synthetic listings,
checks the exact-repeat hit, and saves both HTTP results. Run the exporter
with the two IDs in `smoke.json` to regenerate the A1 JSONL files.

```bash
PYTHONPATH=.:code python -m scripts.hw10.collect_drafts smoke \
  --seed-fixtures --log-dir "$HW10_RUNTIME" --output-dir "$HW10_EXPORT" \
  --owned-cache-namespace "$HW9_CACHE_NAMESPACE"
```

Change `smoke` to `collect` and choose a fresh output directory to produce
`eval_cases.json` and the blank `human_labels.csv`. Run the collector serially
in its own namespace. It removes prior entries only from that namespace before
each new request, then exercises the regular cache lookup and validates the
miss, the actual model attempts, and the delivered Kafka message chain.
The private `collection.jsonl` in the log directory allows resuming from
already verified cases. Score the unchanged draft against the question and
saved facts. The pipeline snapshot includes listing title, property type,
and available units. Some cases deliberately ask about facts absent from
that snapshot.

## Controlled Writer failure for Session D

1. On D's isolated stack, keep the API, Kafka, Planner, Reviewer, and Ollama
   running. Check that `hw10-writer-failure:missing` is absent from the local
   Ollama model list. Stop only D's healthy Writer process. Preserve its
   SQLite stage directory and consumer group.
2. Start the Writer with its usual settings and the same stage directory and
   group, adding `--model hw10-writer-failure:missing`. Use a separate
   `writer-failure.log` in the same runtime log directory. Wait for
   `consumer_ready`.
3. Submit a valid, uncached authenticated question as usual. Ensure the cache
   lookup shows `miss`. The missing model should produce an Ollama error on
   each of three Writer attempts, followed by `dead_letter_published` for
   the same correlation ID. The API waits for its existing 180-second Kafka
   deadline and returns HTTP 504. Use a client timeout greater than 180
   seconds and capture `X-Trace-ID` from the response. Export that ID with
   the command above and cross-check the actual error and dead-letter offset
   in the private Writer log.
4. Stop the failing Writer and restart it with the original model, stage
   directory, and group. Wait for readiness and resubmit the question. The
   previous failure did not store an answer in the cache. Require HTTP 200,
   `is_cached=false`, and a newly linked plan, draft, and final. Keep the
   failure and recovery separate from the 50 measured requests.
