# Homework 5 Part 2 evidence — Pragya Apurva

Implementation, live verification, and the required Inspector evidence are complete for **Parts 2A and 2B only**. The coordinator still owns review, Part 1 integration, later parts, and the final report. Nothing was pushed or submitted.

Original capture revision: `8f24f44b87f83f813a7a60281bfcd523ab141fa1`, branch `codex/hw5-part2-mcp`, based on `f57d20fd5588589fcf6e6c8792b0d912277da9f0`. The original source hashes in `../raw/part2/verified-source-sha256.json` identify that implementation. GUI captures were taken from the same source before the original local code commit. The original evidence was committed in `9658abe26d9f421968cb895bd1a34a197ff1e3fd`.

## Review fixes and refreshed verification

Coordinator review found that FastMCP 1.28.1 discarded unexpected rental-tool arguments before shared validation. The domain transport now uses the official SDK's public low-level `Server` API and publishes the shared input models directly. All three schemas enforce `additionalProperties: false`. Flat arguments, defaults, output schemas, public fields, and the three semantic failure envelopes are preserved. Meals is unchanged. The fixture helper now has finite connect/read/write timeouts of 5/10/10 seconds; its populated database was not reinitialized.

The fix was verified from a working-tree snapshot above `9658abe26d9f421968cb895bd1a34a197ff1e3fd`, before its focused local commit. [Current source hashes](../raw/part2/review-fixes/verified-source-sha256.json) identify the exact tested files; the refreshed STDIO record explicitly marks `working_tree_dirty: true`. [Integrity and provenance](../raw/part2/review-fixes/evidence-integrity.json) bind the new evidence to that snapshot and confirm the original artifacts were preserved.

- **108 tests passed**, including three real STDIO tests with valid controls and reader access logs proving extra fields are rejected before reader access; [output](../raw/part2/review-fixes/pytest.txt).
- The fixture timeout test intercepted SQLAlchemy's effective PyMySQL connection options before driver/network access. No fixture setup was performed on the retained database.
- [Refreshed live rental calls](../raw/part2/review-fixes/domain-stdio.json) preserve all six original requests and application envelopes, plus four native malformed/type/range errors and three extra-field errors.
- [Refreshed Inspector CLI discovery](../raw/part2/review-fixes/rentals-inspector-tools-list.json) matches the shared schemas and Python STDIO discovery for exactly three tools. This is CLI evidence, not a new GUI capture.

Extra fields, missing IDs, Boolean/string IDs, and zero IDs return native `isError:true` results with no application envelope. JSON Schema accepts an integral float such as `1.0`; the strict shared model rejects it with an application envelope before reader access. Whitespace-only queries and absent positive IDs remain the prescribed semantic application failures.

The ten screenshots, original schemas/raw results, and `rejected-cases.json` below remain historical proof from `8f24f44`; they have not been relabeled as captures of the fix. No additional GUI screenshots or Meals API calls were needed for these scoped fixes. The owned MySQL instance was restarted for read-only rental capture, then stopped again.

## Capture mapping

Every image below is a genuine MCP Inspector 1.0.2 browser screenshot. Its corresponding file in `../raw/part2/inspector/` contains the exact request and response copied from that same GUI history entry. The random-meal JSON therefore matches its screenshot, rather than a later random call. Inspector abbreviates some long result strings or collapses nested fields in the viewport; the paired JSON preserves the full output. No screenshots were reconstructed or composited.

| Label | Call and result | Screenshot | Matching raw GUI JSON |
| --- | --- | --- | --- |
| 2A-01 | Name search: `Arrabiata`, limit 5; Spicy Arrabiata Penne | [Search](../screenshots/part2/2A-01-search-meals.jpg) | [JSON](../raw/part2/inspector/2A-01-search-meals.json) |
| 2A-02 | Ingredient: `chicken`, limit 1; Brown Stew Chicken | [Ingredient](../screenshots/part2/2A-02-ingredient.jpg) | [JSON](../raw/part2/inspector/2A-02-ingredient.json) |
| 2A-03 | Random meal, `{}`; returned recipe ID 53105 | [Random](../screenshots/part2/2A-03-random-meal.jpg) | [JSON](../raw/part2/inspector/2A-03-random-meal.json) |
| 2A-04 | Detail ID 52771; full recipe | [Detail](../screenshots/part2/2A-04-meal-details.jpg) | [JSON](../raw/part2/inspector/2A-04-meal-details.json) |
| 2B-01 | Search `Sunny Downtown Apartment`; one public listing | [Search success](../screenshots/part2/2B-01-search-success-mysql3308.jpg) | [JSON](../raw/part2/inspector/2B-01-search-success.json) |
| 2B-02 | Search with three spaces; application error | [Search rejection](../screenshots/part2/2B-02-search-rejected-mysql3308.jpg) | [JSON](../raw/part2/inspector/2B-02-search-rejected.json) |
| 2B-03 | Rental ID 1; public detail | [Detail success](../screenshots/part2/2B-03-detail-success-mysql3308.jpg) | [JSON](../raw/part2/inspector/2B-03-detail-success.json) |
| 2B-04 | Confirmed absent rental ID 8; application error | [Detail rejection](../screenshots/part2/2B-04-detail-rejected-mysql3308.jpg) | [JSON](../raw/part2/inspector/2B-04-detail-rejected.json) |
| 2B-05 | Manager ID 1; Campus Homes has five rentals | [Count success](../screenshots/part2/2B-05-count-success-mysql3308.jpg) | [JSON](../raw/part2/inspector/2B-05-count-success.json) |
| 2B-06 | Confirmed absent manager ID 4; application error | [Count rejection](../screenshots/part2/2B-06-count-rejected-mysql3308.jpg) | [JSON](../raw/part2/inspector/2B-06-count-rejected.json) |

The six domain screenshots show the factual client metadata label `MySQL3308/s6102_rel synthetic`. That label accompanies the request; it is not a tool argument or a fabricated server result. Whitespace validation occurs before SQL, while the server is configured with that same MySQL source.

## Data and runtime provenance

Meals calls used the actual public TheMealDB V1 API with educational key 1. Domain calls used an owned MySQL **8.4.11** instance on `127.0.0.1:3308`, database `s6102_rel`. Seven synthetic rentals and three managers were explicitly initialized from the unchanged HW4 `001_initial.sql` schema. This was new evidence data, not the previous submission database or Part 1's database. The runtime account had SELECT grants on public columns only; reading `submitter_email` was actually denied.

The [fixture identity](../raw/part2/database-fixture.json) records the baseline hash, image identity, row counts, grants, and setup repair. Part 1's MySQL on 3307 and application on 8702 were not altered. Server imports and launches do not migrate or seed.

Python **3.12.13**, official MCP SDK **1.28.1**, and all four Inspector packages **1.0.2** were tested. Inspector ran sequentially on UI 6274/proxy 6277 with authentication enabled; Node **24.19.0** satisfies its declared `>=22.7.5` engine requirement. [Runtime versions](../raw/part2/runtime-versions.json) and [resolved Python packages](../raw/part2/requirements-resolved.txt) preserve the actual versions. Version-specific sources: [Inspector 1.0.2 README](https://github.com/modelcontextprotocol/inspector/blob/1.0.2/README.md), [SDK 1.28.1 metadata](https://github.com/modelcontextprotocol/python-sdk/blob/v1.28.1/pyproject.toml), and [TheMealDB documentation](https://www.themealdb.com/api.php).

## Verification outcomes

| Verification | Actual outcome and evidence |
| --- | --- |
| Dedicated dependencies | `pip check`: no broken requirements |
| Focused tests | Original **104 passed**; current **108 passed**, no skips; [current output](../raw/part2/review-fixes/pytest.txt) |
| Meals STDIO | Initialization, exact four-tool inventory, and all four live calls passed; [record](../raw/part2/meals-stdio.json) |
| Domain STDIO | Initialization, exact three-tool inventory, unchanged semantic envelopes and strict extra-field rejection; [current record](../raw/part2/review-fixes/domain-stdio.json) |
| Inspector discovery | Exact published schemas and inventories: [Meals](../raw/part2/meals-inspector-tools-list.json), [current rentals](../raw/part2/review-fixes/rentals-inspector-tools-list.json) |
| Live MySQL behavior | Twelve literal/Unicode cases, zero-count manager, nullable manager, and private-column denial passed; [checks](../raw/part2/mysql-checks.json) |
| GUI evidence | Four Meals and six domain screenshots, each visually reviewed and paired with its real GUI JSON; [hash manifest](../raw/part2/capture-manifest.json) |

Tests cover normalizers, endpoint parameters, input boundaries, null/empty responses, clean upstream failures, public projections, SQL parameterization, offline injected readers, network-free imports, and true subprocess STDIO calls. The fixture tests are labeled offline and are not presented as the live database evidence.

The one test warning is a `pydantic_settings` unresolved `lifespan` forward-reference warning from the SDK dependency. It did not prevent discovery or calls. It is preserved in the test output rather than suppressed or represented as a test failure.

## Rejected cases preserved for Part 3

[rejected-cases.json](../raw/part2/rejected-cases.json) preserves the actual original GUI requests, original published input schemas, and results. Use the refreshed discovery above for current strict input schemas. The same requests still produce the same envelopes:

```text
search_rentals({"query":"   ","limit":5})
  {"ok":false,"data":null,"error":"Invalid input: query: Value error, query must contain non-whitespace characters"}
get_rental({"rental_id":8})
  {"ok":false,"data":null,"error":"Rental 8 was not found."}
count_rentals({"manager_id":4})
  {"ok":false,"data":null,"error":"Property manager 4 was not found."}
```

IDs 8 and 4 were derived above the actual maximum IDs and independently looked up to confirm absence. These are schema-valid semantic failures, so the MCP result has `isError:false` and the application envelope has `ok:false`. Native malformed/type/range calls are recorded separately in `domain-stdio.json`: missing ID, Boolean ID, zero ID, and string ID `"1"` produce `isError:true` before the handler. No SDK internals or schemas were weakened to disguise that distinction.

## Limits and next integration check

Search follows MySQL lowercase mappings plus `utf8mb4_bin`, not Python casefold. Live evidence confirms accent sensitivity, literal wildcard characters, no `ß` to `ss` expansion, and no normalization of decomposed accents. These semantics are documented in `docs/HW5_PART2.md`.

No required Part 2 captures are missing. The next coordinator check is to rerun all three rental tools against Part 1's migrated schema using a read-only DSN and a new evidence filename. Do not run this session's fixture setup against that database. This session does not claim that future integration check, later homework parts, or the final report are complete.
