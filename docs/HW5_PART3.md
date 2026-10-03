# HW5 Part 3: rental tool reliability

Part 3 covers assignment items 18–21: preserve the three rental tools' contracts, explain the inherited rejected calls, bound transient retries and storage waits, and measure the effect of injected failures. The public tools remain `search_rentals`, `get_rental`, and `count_rentals`.

## Input and result contracts

The authoritative models are in [`contracts.py`](../src/rental_tools/contracts.py). The exact JSON input schemas below are from the reviewed Part 2 [`tools/list` capture](../reports/hw05/raw/part2/review-fixes/rentals-inspector-tools-list.json), checked against those models. The registry remains a static allowlist of these three operations.

### `search_rentals`

Search public listing titles and addresses for literal text and return matching IDs in ascending order. The MySQL reader lowercases both operands and compares with `utf8mb4_bin`; it does not use Python case folding. `%`, `_`, and `!` in the query are escaped as literal search text. Matching is accent-sensitive and does not normalize Unicode or expand `ß` into `ss`.

```json
{
  "type": "object",
  "properties": {
    "query": {
      "maxLength": 255,
      "minLength": 1,
      "title": "Query",
      "type": "string"
    },
    "limit": {
      "default": 5,
      "maximum": 25,
      "minimum": 1,
      "title": "Limit",
      "type": "integer"
    }
  },
  "required": ["query"],
  "additionalProperties": false,
  "title": "SearchRentalsInput"
}
```

The query must be a string of 1–255 characters before trimming, so surrounding spaces count toward the maximum length. The service then strips surrounding whitespace and rejects an empty result. `limit` defaults to 5 and must be an integer from 1 through 25. A successful search returns `data.items`, `data.returnedCount`, and `data.limit`. No matches is a successful empty list.

### `get_rental`

```json
{
  "type": "object",
  "properties": {
    "rental_id": {
      "exclusiveMinimum": 0,
      "title": "Rental Id",
      "type": "integer"
    }
  },
  "required": ["rental_id"],
  "additionalProperties": false,
  "title": "GetRentalInput"
}
```

`rental_id` is a required positive integer. A successful detail lookup returns the public listing fields plus `description`. A structurally valid ID can still be absent from the database; that produces a missing-resource failure after one completed read.

### `count_rentals`

```json
{
  "type": "object",
  "properties": {
    "manager_id": {
      "exclusiveMinimum": 0,
      "title": "Manager Id",
      "type": "integer"
    }
  },
  "required": ["manager_id"],
  "additionalProperties": false,
  "title": "CountRentalsInput"
}
```

`manager_id` is a required positive integer. A successful count returns `managerId`, `managerName`, and `count`. An existing manager with no rentals succeeds with `count: 0`; an absent manager produces a missing-resource failure.

All models forbid additional fields and use strict validation. Python validation rejects Boolean, floating-point, and string values for IDs and `limit`; for example, `true`, `1.0`, and `"1"` are not accepted as integer IDs. JSON Schema's mathematical integer semantics alone do not express every strict Python type distinction. All calls use the shared service validation.

Every application result contains exactly these three keys:

```json
{"ok": true, "data": {"...": "tool-specific public fields"}, "error": null}
```

```json
{"ok": false, "data": null, "error": "A safe explanation."}
```

Search items and detail results expose only `id`, `listingTitle`, `propertyAddress`, `propertyType`, and `managerId`; detail adds `description`. Dependency failures return `Rental data is temporarily unavailable.` Configuration failures return `Rental data is unavailable. Check HW5_MCP_DATABASE_URL configuration.` Raw database exceptions, connection strings, credentials, and SQL are not copied into public errors.

## Three inherited rejected calls

These are the actual Part 2 Inspector outcomes, preserved in [`rejected-cases.json`](../reports/hw05/raw/part2/rejected-cases.json). They are historical observations from the Part 2 synthetic fixture in `s6102_rel` on its owned MySQL instance at port 3308, not new Part 3 captures.

| Tool and exact input | Exact application error | Why it was rejected |
|---|---|---|
| `search_rentals({"query":"   ","limit":5})` | `Invalid input: query: Value error, query must contain non-whitespace characters` | Three spaces satisfy the raw string-length schema, but trimming leaves no search text. Validation rejects this before any storage read. |
| `get_rental({"rental_id":8})` | `Rental 8 was not found.` | The positive ID is structurally valid, but rental 8 was absent in the captured fixture. The completed read is not retried. |
| `count_rentals({"manager_id":4})` | `Property manager 4 was not found.` | The positive ID is structurally valid, but manager 4 was absent in the captured fixture. This is different from an existing manager with zero rentals. |

Each captured result has `ok:false` and `data:null`. The corresponding MCP result has `isError:false`: the transport successfully delivered an application failure envelope. This is distinct from an MCP SDK schema rejection, which can occur before the handler runs. IDs 8 and 4 are not assumed to be absent in every database.

The paired original captures are:

- [`2B-02-search-rejected.json`](../reports/hw05/raw/part2/inspector/2B-02-search-rejected.json), captured at `2026-10-03T08:35:29.025Z`.
- [`2B-04-detail-rejected.json`](../reports/hw05/raw/part2/inspector/2B-04-detail-rejected.json), captured at `2026-10-03T08:36:10.300Z`.
- [`2B-06-count-rejected.json`](../reports/hw05/raw/part2/inspector/2B-06-count-rejected.json), captured at `2026-10-03T08:36:40.541Z`.

The embedded `published_input_schema` values in the historical rejection index predate the reviewed schema correction. They use older schema titles and omit `additionalProperties:false`. Use the reviewed `tools/list` capture and shared models above for the current schema; preserve the historical files unchanged as evidence of the calls and errors.

## Retry and service lifecycle contract

The shared factory has this interface:

```python
build_service(*, reader=None, policy=None, attempt_observer=None) -> RentalService
```

An explicitly supplied reader is selected with `reader is not None`. Otherwise the factory constructs the lazy MySQL reader. Imports and service construction must not connect to MySQL or read secret environment values. The first requested storage read initializes the database engine. The MCP transport keeps `create_server(reader=None)` and the same three tools and schemas.

The service uses exactly one `RetryingRentalReader`. Its position below `RentalService` matters: it sees storage exceptions before the service converts them to a safe result. It never retries an `ok:false` envelope. Invalid input makes no storage attempt; a missing row, empty search, or zero count is a completed read with no retry.

The default policy is:

| Setting | Value | Meaning |
|---|---:|---|
| `max_attempts` | 3 | Includes the initial read. |
| `initial_backoff_s` | 0.1 | Delay before the second attempt. |
| `backoff_multiplier` | 2.0 | Multiplies the previous delay. |
| `max_backoff_s` | 0.2 | Caps each delay. |

There is no baseline jitter, which means there is no random variation added to the delays. Three transient failures cause three reads and exactly two sleeps: 0.1 and 0.2 seconds. There is no sleep after success or the final attempt. Policy values must be finite and sensible; Boolean attempt counts are invalid.

Only an explicit allowlist of temporary I/O failures and the experiment's dedicated transient exception are eligible for retry. Authentication, permissions, bad configuration, invalid database/schema/SQL, input validation, and programmer errors are permanent. An `OperationalError` class alone does not make an error temporary. Exhaustion passes the final exception to the service's existing sanitization.

Attempt observers receive only safe attempt metadata. An observer failure cannot alter a result or trigger another storage read. An already wrapped reader is reused when the requested overrides do not conflict; conflicting overrides are rejected instead of nesting retries. The wrapper's `close()` is idempotent and forwards an available underlying `close()` at most once. Callers own service cleanup.

Part 4's default executor is a later integration consumer of this factory. It will own one service per call and close the reader in `finally` without replacing the result if cleanup fails. An injected service remains caller-owned. Part 3's experiment instead reuses its owned service and closes it at the end. Combined executor verification belongs to U6c.

## What the timeout controls bound

The required settings are the existing PyMySQL connect/read/write controls of 5/10/10 seconds, plus an explicit SQLAlchemy pool acquisition timeout of 5 seconds.

| Control | Default seconds | Wait covered |
|---|---:|---|
| `connect_timeout` | 5 | Establishing the driver socket connection. |
| `read_timeout` | 10 | A driver socket read waiting for server bytes. |
| `write_timeout` | 10 | A driver socket write. |
| `pool_timeout` | 5 | Waiting to acquire a connection when the connection pool is exhausted. |

These controls do not establish a hard deadline for the entire logical tool call. A call can involve several socket operations, pool waits, retries, and backoff sleeps. The read timeout also applies while awaiting protocol data; proving a read timeout during a stalled handshake is not a measurement of a SQL query timeout. The retained defaults require workload-specific tuning before drawing conclusions about interactive response time.

Configuration assertions and a fixture that raises an exception do not prove real I/O timeouts. Part 3 must also retain a bounded actual-driver probe using its own stalled loopback socket or controlled database query, with the shorter probe timeout, observed elapsed time, proved control, scheduling tolerance, and cleanup recorded. Live MySQL reads through STDIO are a separate check.

## Measured experiment design

The controlled benchmark uses a Part 3-owned immutable fixture and the valid input cycle `search_rentals({"query":"campus","limit":5})`, `get_rental({"rental_id":1})`, and `count_rentals({"manager_id":1})`. Rental 1, manager 1, and a matching campus listing must exist in that fixture, so all three calls succeed without injection. Fixture search matching is an approximation for the experiment, not evidence of MySQL collation behavior.

For each configured failure probability 0%, 20%, and 50%, the runner creates a fresh local `random.Random(266102)` and makes 50 logical calls in that round robin: 17 search calls, 17 detail calls, and 16 count calls. Every storage attempt, including attempts at 0%, draws once. A draw below the configured probability raises the dedicated transient exception. Retry attempts consume additional draws; the runner neither reseeds each call nor forces an exact observed failure percentage.

Each duration measures the entire service call with a monotonic clock and real backoff sleeps, including calls that end in failure. The selected dataset must contain exactly 150 JSONL records. Each record preserves its tool/input, failure probability, logical index, final envelope, elapsed milliseconds, attempt count, and ordered draw/injection/outcome/sleep trace. The manifest identifies the seed, policy, fixture hash, tested source revision and hashes, dirty state, versions, UTC timestamps, and exact command.

The summary is derived from those records, with an independent recomputation:

- Success rate is the number of final successes divided by 50.
- Mean latency includes all 50 elapsed times, including failed calls.
- Nearest-rank p99 selects sorted position `ceil(0.99 × 50) = 50`, so it is the maximum of the 50 samples.

The deterministic replay compares call order, draws and injection decisions, attempts, and outcomes. Elapsed times are measured again and need not match byte for byte. Keep replay data labeled separately from the selected measured dataset.

Three separate demonstrations explicitly script immediate success, one transient failure followed by success, and three transient failures followed by a sanitized error. Their actual traces and results are evidence of those controlled sequences, not extra rows in the random experiment.

Retries can recover a temporary failure but add storage attempts and waiting time. An interactive caller may need fewer attempts and shorter waits to meet its response-time budget; a batch job may accept more waiting to complete more work. The observed table should quantify this tradeoff for the measured fixture. With only 50 samples per probability, p99 is coarse. Fixture timings omit real database and model costs, and later executor measurements use a different service lifetime. The theoretical probability `1 - p**3`, if discussed, is a model of three independent attempts, not a replacement for observed success counts.

## Running and evidence status

Run from this worktree with its own Python 3.12 environment and the existing pinned `requirements-mcp.txt`. Keep database configuration outside Git. Start the domain STDIO server with:

```bash
python -m src.mcp_servers.rentals
```

Its stdout is reserved for MCP protocol messages. The lazy MySQL reader requires `HW5_MCP_DATABASE_URL` to select the `mysql+pymysql` driver and database `s6102_rel`. The Part 3 live gate must use a positively identified Part 3-owned database instance; existing Part 1 and Part 2 services and historical evidence remain read-only.

The focused checks cover the four Part 3 suites and relevant inherited domain/STDIO behavior:

```bash
python -m pytest tests/test_hw05_reliability.py tests/test_hw05_runtime.py tests/test_hw05_fault_experiment.py tests/test_hw05_timeouts.py tests/test_hw05_domain_tools.py tests/test_hw05_mcp_stdio.py
python -m pip check
```

**Evidence pending:** This initial operating guide records source contracts and the required experiment design. It does not yet claim that the new implementation, actual-driver probe, demonstrations, 150-call measured run, replay, or live MySQL STDIO gate has passed. Final commands, measured results, source provenance, and any remaining gaps must be recorded under `reports/hw05/part3/` and linked here after verification. U5/U6c combined integration is a separate coordinator gate.
