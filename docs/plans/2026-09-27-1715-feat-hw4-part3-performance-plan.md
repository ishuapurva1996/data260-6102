---
title: "feat: HW4 Part 3 measured N+1 query tuning"
date: 2026-09-27
type: feat
artifact_contract: ce-unified-plan/v1
product_contract_source: course-assignment
execution: code
---

# HW4 Part 3: N+1 measurement and query tuning

## Goal Capsule

**Objective:** Demonstrate, with reproducible MySQL measurements, how fetching related data per rental changes query count and response time, and explain an observed index-plan change.

**Means:** Deterministic dataset, equivalent naive/joined endpoints, 180 measured requests and an index/EXPLAIN experiment under the [shared contract](2026-09-27-1715-hw4-shared-contract.md).

**Authority:** User instructions and HW4 PDF → shared contract → this plan. Own Part 3 code, measurement and evidence; Part 2 owns shared backend foundations and integration. Commit locally, without deployment, publishing or submission tags.

---

## Product Contract

### Summary

Create two authenticated list implementations returning the same rental-and-manager data, measure their SQL and HTTP cost, then document what adding one index changes.

### Problem Frame

Moving records into MySQL makes query design visible in application performance. A list can return correct data while making one extra database round trip for each row. The assignment requires a controlled comparison, not an assumed speed-up.

### Requirements

| ID | Required result | Assignment source |
| --- | --- | --- |
| R1 | Seed 5,000 rentals and 200 associated rows using SEED 6102; commit generator and schema/migration. | Part 3.1–2 |
| R2 | Naive list actually performs one additional related-data query per record; response includes related data. | Part 3.3 |
| R3 | Fix N+1 using a join/eager loading with equivalent payloads and pagination. | Part 3.5 |
| R4 | Measure 30 requests per page size 10/50/200 per version; preserve all 180 selected-run raw rows. | Part 3.4/6 |
| R5 | Report SQL statements/request and p50/p95/p99 latency, speed-up by size and an explanation grounded in observations. | Part 3.4/7 |
| R6 | Add one index; save the same query's EXPLAIN before/after and explain the observed difference. | Part 3.8 |
| R7 | Capture real Postman output for both versions at all three page sizes; pair code and evidence in the report fragment. | Part 3.9 / submission instructions |

### Scope Boundaries

No related-entity CRUD is required. Do not change authentication or independently create shared database models. Do not optimize unrelated functions or add artificial sleeps to make speed-ups look larger. No RAG work or complete homework submission is included.

---

## Planning Contract

### Key Technical Decisions

- KTD1. Use the foundation's Rental → PropertyManager relation, nullable for ordinary app records and populated for all benchmark rentals. Generate 200 managers with deterministic names and 5,000 rentals assigned across them.
- KTD2. Explicitly execute a manager SELECT for each naive row. Do not rely on lazy access or `Session.get`, because repeated manager IDs may reuse the ORM identity map.
- KTD3. The fixed version uses a left join/eager load in one data query. Both endpoints use identical fields, id ordering, auth, pagination and serialization; register their literal paths before the dynamic ID route.
- KTD4. Instrument actual request-local SQL execution, including auth/activity queries and serialization. Total SQL is the required reported count; a separate data-query count explains the algorithm. No formula may substitute for measurement.
- KTD5. Run serial HTTP requests after warmups, alternate naive/fixed consistently, keep index/cache/setup conditions recorded, and use a monotonic timer. Report the chosen percentile convention; 30 samples make tail percentiles sensitive to the slowest observations.
- KTD6. Demonstrate a new listing-title index with a selective equality query after the N+1 benchmark. Preserve identical data/query and save index inventory so the before state demonstrably lacks this index.

### Dependencies

Design the generator, measurement file schema, summarizer and tests before the backend is ready. Merge Part 2 foundation B before implementing live SQL/router integration. Do not create a second MySQL connection/auth stack. Real measurements depend on a working dedicated MySQL instance and exclusive evidence access to port 8702. Tests on auxiliary ports are development results until the final evidence run.

---

## Implementation Units

### U1. Prepare reproducible data and measurement artifacts

**Goal:** Make the experiment repeatable and its outputs checkable. **Requirements:** R1, R4. **Dependencies:** Contract for design; foundation B for live insertion.

**Files:** `scripts/hw04/part3/seed_data.py`, `scripts/hw04/part3/README.md`, `tests/test_hw04_part3.py`, `reports/hw04/raw/part3/` configuration/seed manifests.

**Approach:** Generate values with the fixed seed, valid six-field rental payloads, a deterministic manager distribution and selective unique titles suitable for the index test. Use an explicitly disposable experiment instance. Record row counts and association checks. Rerunning a seed must not destroy an unrelated database; guard reset behavior by explicit configuration and verified experiment ownership.

**Test scenarios:**
- The same seed gives the same dataset; 5,000 rentals reference exactly 200 existing managers.
- Domain validation passes and IDs/order yield full pages at all required sizes.
- Reset/seed refuses an unverified shared target and preserves unrelated records outside its dedicated instance.

**Verification:** Save actual counts, schema revision and dataset/configuration identity. Reference Part 2's committed base migration instead of making a competing copy.

### U2. Build equivalent naive/fixed endpoints and SQL counters

**Goal:** Isolate query strategy as the difference being measured. **Requirements:** R2–R3, R5. **Dependencies:** Foundation B and U1 dataset.

**Files:** `code/web_application/routers/performance.py`, `code/web_application/query_metrics.py`, the small registration seam in `main.py`, `tests/test_hw04_part3.py`.

**Approach:** Use foundation models, engine and auth dependency. Implement the exact shared routes and response shape. Count SQL execution events with request-local state that remains correct across FastAPI execution contexts; avoid a shared global counter. Include post-handler serialization work. Expose counts through a documented experiment-only response header or correlated measurement record without logging sensitive query parameters.

**Test scenarios:**
- Naive/fixed payloads match at sizes 10, 50 and 200, including manager objects and ordering.
- Naive data queries are N+1 even when managers repeat; fixed data queries remain one with the chosen join.
- Measured total includes auth/session activity; consecutive or overlapping requests do not share counters.
- Missing sessions return 401; invalid sizes/offsets return validation errors; null manager and empty-page results serialize correctly.

**Verification:** Confirm counters against actual executed SQL on real MySQL. Do not change the required behavior to fit predicted totals.

### U3. Collect 180 measured requests and summarize results

**Goal:** Produce auditable timings and speed-up tables. **Requirements:** R4–R5. **Dependencies:** U2, verified equal payloads and a coordinated quiet evidence run.

**Files:** `scripts/hw04/part3/benchmark.py`, `summarize.py`, `tests/test_hw04_part3.py`, `reports/hw04/raw/part3/`, `reports/hw04/part3/METRICS.md`.

**Approach:** Authenticate outside measurement, retain cookies, warm up outside the dataset, and run exactly 30 measured requests per size/version. Record run ID, timestamp, commit and dirty state, database/schema/seed configuration, size, version, iteration, status, returned count, elapsed milliseconds and real query counts. A selected successful run has 180 validated rows; preserve failed attempts separately and rerun complete affected experiment consistently. Compute p50/p95/p99 and naive/fixed latency ratios directly from raw data, naming the statistic used for each ratio.

**Test scenarios:**
- Summary computation reproduces values from known small fixtures and the selected raw run.
- The runner detects wrong counts, 401/500 responses, payload mismatch and incomplete groups instead of reporting success.
- Login/warmup rows are excluded; all six groups contain exactly 30 measured requests.

**Verification:** Recompute the six-row metrics table from saved raw files. Explain actual scaling, overhead and noise; do not assert every size became faster unless the measurements show it.

### U4. Demonstrate index behavior and finish evidence

**Goal:** Explain the database's observed plan and deliver complete Part 3 evidence. **Requirements:** R6–R7. **Dependencies:** U3's benchmark at a consistent index state.

**Files:** `code/web_application/migrations/003_*`, `scripts/hw04/part3/index_experiment.py`, Postman collection under `reports/hw04/part3/`, `REPORT_SECTION.md`, `RUN_LOG.txt`, `AI_USE.md`, `HANDOFF.md`, raw EXPLAIN/index files and screenshot directories.

**Approach:** Save the schema/index inventory and exact equality query before adding the new index. Add the index through the committed migration, rerun the same query's EXPLAIN and verify identical results. Compare access type, chosen key and estimated rows using MySQL's actual output. Capture real Postman screenshots for all six endpoint/size pairs. Present code snippets beside outputs and plain-language explanations of N+1, percentiles, speed-up and indexing.

**Test scenarios:**
- Before/after evidence uses the same query, parameters and dataset and clearly records the new index.
- Query results remain equal; a repeated run handles an existing index without mislabeling the before state.
- Every required size/version screenshot is present or explicitly listed for manual capture.

**Verification:** Deliver the committed code and scripts, complete 180-row dataset, reproducible summary, EXPLAIN evidence and accurate handoff. Include the exact measured revision so Part 2 can decide whether integration requires a full rerun.

---

## Verification Contract

Use real MySQL to prove SQL execution counts, joins, foreign keys and EXPLAIN behavior. Unit tests can check the summarizer and guards, but SQLite or mocked timings cannot satisfy the experiment. Confirm naive/fixed response equality before timing and keep the same authentication/account/index conditions. Measure one worker without reload and without competing heavy workloads.

The final handoff supplies commands established during implementation, actual runtime versions, dedicated instance details without secrets, raw/result paths, measured commit and pending capture/integration steps. No fabricated measurements or Postman substitutes.

## Definition of Done

R1–R7 hold, all 180 selected-run measurements are retained and summaries recompute from them. The counter shows actual executed SQL; the naive/fixed comparison returns equivalent data. EXPLAIN before/after and six Postman screenshots are delivered or specific external evidence gaps are disclosed. Own changes are committed, abandoned experiment code is removed, and the shared handoff enables Part 2 to merge and rerun checks. Part 4 and final submission remain outside this plan.
