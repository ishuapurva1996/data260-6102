# HW5 Part 4: Safe executor and offline assertions

Part 4 implements assignment items 22–24. The future agent calls
`execute_tool(name, inputs)` to access the same three rental operations as MCP.
Each ordinary outcome is a JSON string containing exactly `ok`, `data`, and
`error`. The offline runner exercises the production service, input models,
registry handlers, public projections, and executor using a small in-memory
reader. It needs no database, DSN, network, Inspector, or model server.

## Run the offline checks

From the repository root, use a dedicated Python 3.12 environment and the existing
MCP requirements. Keep it separate from the web application environment.

```bash
python3.12 -m venv .venv-part4
.venv-part4/bin/python -m pip install -r requirements-mcp.txt
.venv-part4/bin/python -m pip check
.venv-part4/bin/python scripts/hw05/run_offline_tests.py
.venv-part4/bin/python -m pytest \
  tests/test_hw05_executor.py tests/test_hw05_offline_runner.py \
  tests/test_hw05_domain_tools.py
```

The selected verification used its own externally stored environment; exact
versions, commands, source hashes, and outcomes are recorded under
`reports/hw05/raw/part4/`. The requirements manifest is unchanged.

The runner prints `Pragya Apurva`, one actual PASS or FAIL per case, then the
number passed out of the total. It continues after an assertion or ordinary
exception fails and exits 1 if any case fails. Exceptions are identified by
type, without printing their potentially sensitive messages. `-O` and `-OO`
disable Python assertions, so the runner rejects those modes with exit 2.
Normal successful execution exits 0. The optional Python-only `main(cases=...)`
seam supports the focused failure test and later Part 5 additions; no deliberately
failing case is enabled in the normal runner.

## Executor contract

```python
from src.rental_tools.executor import execute_tool

# Production signature; Part 3 runtime must be integrated before live use.
result_json = execute_tool("get_rental", {"rental_id": 1})
```

The keyword-only `service` argument permits offline dependency injection:

```python
from scripts.hw05.part4.fixture import FixtureReader
from src.rental_tools.service import RentalService

service = RentalService(FixtureReader())
result_json = execute_tool("get_rental", {"rental_id": 1}, service=service)
```

The executor checks the tool name against the immutable three-tool registry,
requires a dictionary with string keys, and validates raw values with that
entry's shared Pydantic model before constructing any default service. Boolean,
floating-point, and string IDs are rejected rather than converted to integers.
Extra fields are rejected. Caller input is not changed. Only the registry's
stored handler can run; no caller-selected attribute, import, SQL, or expression
is executed. The shared service retains responsibility for domain behavior and
public field selection.

Validation messages use the service's existing formatter, including the exact
whitespace rejection below. The location of each unexpected field is redacted
to `unexpected_field`, producing `unexpected_field: Extra inputs are not permitted`
within that shared format. An unknown field name could itself contain private
data or SQL and must not be reflected in an error. Other declared-field errors
in the same call are preserved. Unknown names and other malformed inputs also
receive fixed messages.
Dependency and unexpected exceptions are converted to sanitized failures.
`KeyboardInterrupt` and `SystemExit` propagate.

Success requires `ok: true`, a dictionary `data`, and `error: null`. Failure
requires `ok: false`, `data: null`, and a nonempty string `error`. Extra envelope
keys, invalid combinations, cycles, NaN, infinity, and nonserializable values
produce the constant failure `Rental tool returned an invalid result.`.
Serialization uses `allow_nan=False`; raw exception text is never returned.
Search with no matches and a known manager with zero rentals remain successes.

## Service and reader ownership

An explicitly injected service is used without importing Part 3's runtime or
reading live configuration. Its reader remains caller-owned and is never closed
by the executor.

A default call lazily imports `src.rental_tools.runtime.build_service()` after
validation, creates one service for that call, and closes its reader in `finally`.
Cleanup happens after success, domain failure, unexpected handler failure, or
serialization failure. A cleanup exception cannot replace the result; the only
allowed diagnostic is `Rental tool cleanup failed.` on stderr. There is no
process-global service cache.

This Part 4 branch intentionally starts at the reviewed Part 2 revision and
does not contain the Part 3 runtime. A structurally valid default call therefore
returns `Rental tool runtime is unavailable.`. No fallback reader or copied
runtime is included. Focused tests use clearly labeled module doubles to check
factory and cleanup glue; they do not prove the real factory or retries work.

Creating and closing a service per production call can add setup and connection
cost. Part 3's experiment reuses a service and closes it when the experiment
ends, so its latency cannot be assumed to equal later default-executor latency.

## Fixture and canonical cases

The fixture has rental IDs 1, 2, 7 and manager IDs 1, 2, 3. Rentals 1 and 2
belong to Alex Morgan (manager 1); rental 7 belongs to Taylor Reed (manager 2).
Manager 3, Empty Manager, has no rentals. Rental 8 and manager 4 are absent.
Rows contain synthetic private-field sentinels so exact public projections
demonstrate exclusion. These are controlled fixture rows, not a MySQL dataset.
The simple literal matching supports these ASCII examples and is not a MySQL
Unicode/collation emulator; inherited SQL tests and later live checks cover that
separate boundary.

| Assertion | Input | Expected result |
| --- | --- | --- |
| `valid_search` | `{"query":"garden","limit":5}` | Public rows 1 and 2 in order, `returnedCount: 2`, `limit: 5` |
| `whitespace_search_rejected` | `{"query":"   ","limit":5}` | Exact inherited validation error, no reader calls |
| `valid_rental_detail` | `{"rental_id":1}` | Exact six-field public projection, including description |
| `missing_rental_8_rejected` | `{"rental_id":8}` | `Rental 8 was not found.` |
| `valid_manager_count` | `{"manager_id":1}` | Manager 1, Alex Morgan, count 2 |
| `missing_manager_4_rejected` | `{"manager_id":4}` | `Property manager 4 was not found.` |

The exact whitespace error is:

```text
Invalid input: query: Value error, query must contain non-whitespace characters
```

Every case asserts string return type, valid JSON, exactly three envelope keys,
success/failure invariants, and meaningful exact data or error. Each case also
checks the expected reader calls. The three rejected calls match the original
Inspector outputs referenced by `reports/hw05/raw/part2/rejected-cases.json`.
Those historical captures describe their original fixture and schema snapshots;
current strict schemas are in
`reports/hw05/raw/part2/review-fixes/rentals-inspector-tools-list.json` and the
shared models. Historical evidence is unchanged. Missing IDs in that original
database are not assumptions about every future database.

## Evidence and remaining integration

See `reports/hw05/part4/EVIDENCE.md` for selected text evidence, source provenance,
and the separately reported terminal screenshot status. Tests guard network and
database constructors and live configuration reads before importing the runner,
then execute all six cases. Subprocess tests verify repeatability, actual failure
exit status with a complete summary, and rejection of optimized Python.

Coordinator gate U6c must integrate the real Part 3 factory, verify all three
default tool calls through its retrying reader, check retry and cleanup behavior,
and compare executor and MCP outputs against an owned upgraded `s6102_rel`
database. It must also verify strict schemas and absence of credential leakage.
Offline fixture tests and lifecycle doubles are not substitutes for that gate.
Part 5's safety rule, contact flag, agent loop, and additional tests are outside
this implementation.
