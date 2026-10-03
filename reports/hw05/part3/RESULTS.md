# Part 3 — Tool contracts under stress

**Pragya Apurva · DATA 260 · Homework 5**
`DOMAIN_ID=6`, `SID4=6102`, `PORT_BASE=8702`, `PREFIX=s6102`, `SEED=6102`, `VERIFY_SEED=266102`.

Code and tests are complete for Part 3. All required numerical, scripted, actual-driver, and live MySQL checks passed. Genuine Terminal screenshots remain pending because native capture omitted the application window. U5/U6c combined integration remains the coordinator's work; this is not whole-homework acceptance.

## 18. Contracts and inherited rejections

The [operating guide](../../../docs/HW5_PART3.md) includes the exact current JSON input schemas, public result fields, and explanations. The current schemas forbid extra properties and preserve strict Python types. They are verified against the reviewed Part 2 tools/list capture; older schema metadata embedded in historical captures is not presented as current.

| Tool | Preserved rejected JSON input | Exact returned error |
|---|---|---|
| `search_rentals` | `{"query":"   ","limit":5}` | `Invalid input: query: Value error, query must contain non-whitespace characters` |
| `get_rental` | `{"rental_id":8}` | `Rental 8 was not found.` |
| `count_rentals` | `{"manager_id":4}` | `Property manager 4 was not found.` |

Each result is `{"ok":false,"data":null,"error":<shown message>}`. Whitespace fails validation before storage. IDs 8 and 4 were absent in the original Part 2 fixture, so those reads completed but found no row. Missing records are not temporary storage failures. The original [rejection evidence](../raw/part2/rejected-cases.json) is unchanged. Its MCP `isError:false` means the protocol delivered the application envelope successfully; native schema errors are a separate case.

## 19. Bounded retries and timeouts

[`RetryingRentalReader`](../../../src/rental_tools/reliability.py) wraps storage below `RentalService`, so final exceptions reach the existing sanitized error conversion. All three reads share a policy of three attempts, a 0.1-second first delay, multiplier 2, and 0.2-second delay cap. Three failures therefore cause only two sleeps. The factory reuses an existing wrapper instead of nesting retries, stays lazy, and exposes idempotent cleanup.

The relevant retry decision is:

```python
transient = is_transient(error)
retry = transient and attempt < self.policy.max_attempts
# The observer receives safe metadata here.
if not retry:
    raise
self._sleep(delay)
delay = min(delay * self.policy.backoff_multiplier,
            self.policy.max_backoff_s)
```

The [separate scripted demonstrations](../raw/part3/demos/demonstrations.json) produced these actual results. They explicitly choose failure sequences; they are not random observations from the 150-call sample.

| Scripted case | Attempts | Sleeps (seconds) | Final ok | Actual elapsed (ms) |
|---|---:|---|---|---:|
| immediate_success | 1 | none | True | 0.062417 |
| transient_then_success | 2 | 0.1 | True | 105.077667 |
| retry_exhaustion | 3 | 0.1, 0.2 | False | 305.498792 |

Exhaustion returns the actual clean result:

```json
{"ok": false, "data": null, "error": "Rental data is temporarily unavailable."}
```

The small classifier allows specified socket failures, pool timeouts, and recognized MySQL transient codes. Authentication, permissions, bad SQL/schema/configuration, and programmer errors are not retried. Whitespace performs zero reads; missing rows, empty searches, and zero counts complete without retry. Observer exceptions cannot cause another storage read.

The reader retains connect/read/write timeouts of 5/10/10 seconds and adds a 5-second pool-acquisition timeout. Each limits a particular wait, not the whole logical call. The [actual-driver receipt](../raw/part3/driver-timeout.json) used a separate owned stalled loopback greeting with read timeout **0.2 seconds**. It returned after **218.345917 ms**, within its 150–1700 ms tolerance, as SQLAlchemy OperationalError wrapping PyMySQL OperationalError **2013**. The listener and accepted socket closed and the server thread stopped. This proves the driver read wait during the greeting, not a SQL query deadline or connect/write/pool timing.

The [live STDIO receipt](../raw/part3/live-stdio.json) separately verifies real MySQL 8.4.11 on the owned port 3310: unchanged inventory and schemas, three successful tool calls, the three inherited application-error cases, empty search, zero count, and three native extra-field rejections. This database has seven synthetic rental rows and three managers, initialized from retained HW4 schema; it is separate from the experiment fixture and other sessions' databases.

## 20. Selected 150-call experiment

The immutable fixture has rental 1 (`Campus apartment`) assigned to manager 1 (`Campus Homes`). The fixed cycle searches `campus` with limit 5, gets rental 1, and counts manager 1. Each rate contains 17 searches, 17 detail reads, and 16 counts. Every input succeeds without injection. Python fixture matching does not prove MySQL collation semantics.

Each rate starts a new local `random.Random(266102)` and draws once per storage attempt, even at 0%. A draw below the rate injects one transient error. Retries consume extra draws. The whole service call is timed with `perf_counter`, including validation, actual sleep, and final failures. The service is reused within each rate and closed afterward. These measurements omit MySQL and model costs and do not include Part 4's per-call default-service setup.

| Injected failure rate | Success rate | Mean latency (ms) | Nearest-rank p99 (ms) | Storage attempts |
|---|---:|---:|---:|---:|
| 0% | 50/50 (100%) | 0.009701 | 0.323083 | 50 |
| 20% | 50/50 (100%) | 20.548434 | 302.708542 | 59 |
| 50% | 46/50 (92%) | 109.071352 | 310.386083 | 90 |

The sole selected dataset is [selected/rows.jsonl](../raw/part3/selected/rows.jsonl), with [manifest](../raw/part3/selected/manifest.json) and [metrics](../raw/part3/selected/metrics.json). A separately labeled replay also contains 150 rows; it is not combined with this table. [Replay comparison](../raw/part3/replay/replay-comparison.json) matched every draw, injection, input, attempt, delay, and outcome. Wall-clock values appropriately differed.

An [independent standard-library audit](../raw/part3/independent-recomputation.json), implemented in [recompute_metrics.py](../../../scripts/hw05/part3/recompute_metrics.py), rebuilt every RNG draw and recalculated the table without importing the experiment implementation. It enforced 50 rows per rate and the fixed 17/17/16 mix. The mean uses all 50 durations, including failures. Nearest-rank p99 is position `ceil(0.99*50)=50`, the sample maximum.

## 21. Interactive versus batch use

At 20% injection, 42 calls succeeded on their first attempt; retries recovered the other 8 and raised final success to 50/50. This took 59 storage attempts instead of 50, an 18% increase, and mean latency rose to 20.548 ms. At 50% injection, 23 calls succeeded immediately and retries recovered 23 more. Four exhausted the policy; 90 attempts meant 80% more storage work. Mean latency was 109.071 ms and the slowest call took 310.386 ms.

The backoff itself adds at most 0.3 seconds per logical call, which may be acceptable for an interactive assistant. The retained 5/10/10-second I/O controls can produce much longer real delays across retries, so this fixture result does not establish an interactive deadline. For an interactive workload I would measure a shorter configuration, such as two attempts, a 0.05-second retry delay, and lower connection/read/pool waits chosen against a response-time budget. Shortening waits can also reject healthy but slow operations, so those choices require real workload measurements.

For batch processing I would evaluate four or five attempts with longer capped delays (for example 0.5, 1, then 2 seconds) when extra waiting is acceptable, while keeping finite I/O waits and treating permanent errors as final. More attempts increase both completion chances and load. Fifty samples per rate give a coarse p99 estimate—the maximum observed here—and the requested injected probability does not force an exact observed percentage. No theoretical success rate is substituted for these measurements.

## Verification and provenance

- Focused Part 3 plus inherited rental domain/STDIO suites: **194 passed, 0 failed, 0 skipped**; one unrelated Meals fixture test deselected.
- `pip check`: no broken requirements. Python 3.12.13; MCP 1.28.1; Pydantic 2.12.5; SQLAlchemy 2.0.48; PyMySQL 1.1.2. [Full installed versions](installed-versions.txt).
- Demonstrations, selected experiment, replay, real timeout, and MySQL smoke ran on clean code revision `ca4641778c34cf14c1ed07aea63be20374d5306f`. Tests ran immediately before that commit on identical code/test bytes.
- Source and artifact hashes, actual UTC timestamps, command lines, fixture hash, and dirty flags are in the manifests; the selected run began `2026-10-03T22:46:58.423208+00:00`. [Run log](RUN_LOG.txt), [test transcript](tests.txt), and [evidence manifest](EVIDENCE_MANIFEST.json) retain the details.
- These receipts are programmatic and terminal-text evidence, not Inspector or GUI screenshots. Genuine named Terminal captures remain pending. No screenshot has been fabricated from copied console text.
- The owned MySQL container was stopped after verification; its external data/configuration remain available for a coordinator restart. [Cleanup receipt](../raw/part3/runtime-cleanup.json).
- Part 1's upgraded schema and the combined Part 4 default executor, cleanup, and output parity still require coordinator U5/U6c verification. Part 5 is untouched.
