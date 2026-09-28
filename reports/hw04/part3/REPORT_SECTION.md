# HW4 Part 3 — Measured N+1 queries and a listing-title index

SID4 **6102**; PORT_BASE **8702**; PREFIX **s6102**; SEED **6102**; VERIFY_SEED **266102**; DOMAIN_ID **6**, Rental Housing Listings. Hardware: Apple M4, 10 CPU cores, 24 GiB memory. MySQL 8.4.11 runs in a dedicated Docker instance; Python 3.13.5 runs the shared FastAPI service. No language model is used by this performance experiment. This is a Part 3 fragment; Part 4, the complete PDF and the final hw4 submission tag are outside its scope.

## 3.1–3.2: Reproducible related data

A rental is one row describing a listing. Its `manager_id` refers to one property-manager row. Several rentals can share that manager; this is a many-to-one relationship. The foundation owns both tables and the foreign key in `code/web_application/migrations/001_initial.sql`, imported through commit `f29e7cc85baf52bea30bd4bb3209d1bd79b22051`.

The generator uses a local random-number generator with seed 6102, shuffles 25 copies of manager ordinals 1–200, and creates 5,000 valid six-field rental records. A unique listing title supports the later selective index query. IDs are assigned by MySQL.

```python
def generate_dataset(seed: int = SEED) -> dict:
    """Return a stable, domain-valid dataset with exactly 25 rentals per manager."""
    rng = random.Random(seed)
    manager_ordinals = list(range(1, MANAGER_COUNT + 1)) * (RENTAL_COUNT // MANAGER_COUNT)
    rng.shuffle(manager_ordinals)
    streets = ("Cedar", "Willow", "Maple", "Oak", "Pine", "Elm", "Birch", "Laurel")
    neighborhoods = ("Downtown", "Rose Garden", "Willow Glen", "Japantown", "Alum Rock")
    managers = [{"ordinal": i, "name": f"HW4 Property Manager {i:03d}"} for i in range(1, MANAGER_COUNT + 1)]
    rentals = []
    for ordinal, manager_ordinal in enumerate(manager_ordinals, start=1):
        property_type = rng.choice(PROPERTY_TYPES)
        neighborhood = rng.choice(neighborhoods)
        rentals.append({
            "listing_title": f"HW4-{seed}-{ordinal:05d} {property_type.title()} in {neighborhood}",
            "property_address": f"{100 + ordinal} {rng.choice(streets)} Street, San Jose, CA 95112",
            "submitter_email": f"landlord{manager_ordinal:03d}@example.com",
            "description": f"Well maintained {property_type} in {neighborhood}, with a bright living area and convenient access to local amenities.",
            "property_type": property_type,
            "terms_accepted": True,
            "manager_ordinal": manager_ordinal,
        })
    return {"format_version": 1, "seed": seed, "managers": managers, "rentals": rentals}
```

Actual MySQL seed output:

```json
{
  "actual_counts": {
    "associated_rentals": 5000,
    "distinct_managers": 200,
    "property_managers": 200,
    "rentals": 5000,
    "unique_listing_titles": 5000
  },
  "generated_dataset_sha256": "9513ac766ab94f7c23c9257536d8e0f623c8bcbf530f6881e3c354cc7ced1b78",
  "stored_dataset_sha256": "9513ac766ab94f7c23c9257536d8e0f623c8bcbf530f6881e3c354cc7ced1b78",
  "rental_id_range": {
    "max": 5000,
    "min": 1
  }
}
```

The generated and stored checksums match after reloading the ORM objects. All 200 managers have exactly 25 rentals. Seeding checks the external ownership manifest, live MySQL UUID and Docker port before writing. It refuses existing rentals/managers and does not alter auth records. A real repeat invocation was refused without reseeding; the expected refusal is retained in `RUN_LOG.txt`.

Evidence: `raw/part3/seed_manifest.json`, `raw/part3/prebenchmark_database.json`; source: `scripts/hw04/part3/seed_data.py`. The seeder checks the actual foundation migration journal and checksums, rather than claiming an unverified schema.

## 3.3 and 3.5: The naive query and equivalent join

To show N+1, first fetch one page of rentals, then perform one manager lookup per rental. For N rentals this needs N+1 data statements. SQLAlchemy's identity map remembers loaded objects inside a session; `Session.get` could reuse an object and avoid the extra query. The explicit SELECT below always goes to MySQL, even for repeated manager IDs.

```python
@router.get('/naive', response_model=list[PerformanceRentalResponse])
def naive(page_size: int = Query(10, ge=1, le=200), offset: int = Query(0, ge=0),
          db: Session = Depends(get_db)):
    rentals = db.scalars(select(Rental).order_by(Rental.id).limit(page_size).offset(offset)
                         .execution_options(hw4_data_query=True)).all()
    rows = []
    for rental in rentals:
        # An explicit SELECT always executes, even when the same manager is
        # already in the ORM identity map. Session.get/lazy access would hide N+1.
        manager = db.scalar(select(PropertyManager).where(PropertyManager.id == rental.manager_id)
                            .execution_options(hw4_data_query=True))
        rows.append(_serialize(rental, manager))
    return rows
```

The fixed version joins rentals to managers in one data statement. A left join keeps a rental even if its manager is null. Both implementations share the same ordering, pagination, ordinary-field serializer and response validation.

```python
@router.get('/fixed', response_model=list[PerformanceRentalResponse])
def fixed(page_size: int = Query(10, ge=1, le=200), offset: int = Query(0, ge=0),
          db: Session = Depends(get_db)):
    rows = db.execute(select(Rental, PropertyManager)
                      .outerjoin(PropertyManager, Rental.manager_id == PropertyManager.id)
                      .order_by(Rental.id).limit(page_size).offset(offset)
                      .execution_options(hw4_data_query=True)).all()
    return [_serialize(rental, manager) for rental, manager in rows]
```

Real HTTPS development smoke checks on auxiliary port 8733 returned equal full payloads at all three sizes. These checks are separate from the final port 8702 latency dataset. Example actual response row:

```json
{
  "listingTitle": "HW4-6102-00001 Condo in Rose Garden",
  "propertyAddress": "101 Oak Street, San Jose, CA 95112",
  "submitterEmail": "landlord020@example.com",
  "description": "Well maintained condo in Rose Garden, with a bright living area and convenient access to local amenities.",
  "propertyType": "condo",
  "termsAccepted": true,
  "id": 1,
  "manager": {
    "id": 20,
    "name": "HW4 Property Manager 020"
  }
}
```

The real-MySQL test additionally set nine page rows to the same manager and one to null under a transaction, then rolled back. The naive version still made 11 data statements; the join made 1. Concurrent requests retained independent counts.

## 3.4 and 3.6: Measurement method and raw evidence

Authentication loads the session/user and updates last activity. Those statements belong to the request cost. The counter starts before dependencies, observes SQLAlchemy cursor executions, and returns totals after JSON serialization. Data statements are tagged separately; reported counts are observed, not calculated from page size. `raw/part3/sql_execution_evidence.json` preserves actual statement shapes and separate-listener counts for all six groups, without bound parameter values.

```python
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    counts = _counts.get()
    if counts is not None:
        with counts.lock:
            counts.total += 1
            if context.execution_options.get('hw4_data_query', False):
                counts.data += 1
```

DBAPI connection setup, pool ping and transaction protocol commands are outside SQLAlchemy's cursor-statement event count, but their time remains inside the HTTP measurement. The two endpoints are ordinary fully materialized JSON responses, not streams.

The runner logs in outside measurement, validates full naive/fixed equality for 10, 50, 200 rows, and performs three warmups per group. It then records 30 serial requests per endpoint/size, alternating naive then fixed for each iteration: exactly 180 selected rows. A monotonic timer surrounds each buffered HTTPS request; JSON validation happens afterward. Every measured response must still equal its preflight baseline. Raw files include run ID, UTC timestamp, actual code revision/dirty state, configuration hash, status, row count, elapsed milliseconds and observed total/data SQL. Failed attempts are never combined with the successful run.

Percentiles sort the 30 timings and use R7 linear interpolation at rank `(n−1) × p`. p50 is the middle of the observations. p95 and p99 describe the slow tail; at only 30 samples, they depend strongly on the slowest few requests. The experiment uses warm caches and one worker without reload. Parts 1/2 coordinated a quiet slot; unrelated pre-existing services were preserved, so incidental system noise remains possible.

## 3.7: Observed latency and speed-up

The selected run is `20260928T003859.945761Z-cd277c20`, executed from clean revision `9860a20342072168ed68a8d41eb16d9bfecf7729` on HTTPS port 8702. Its interval was 2026-09-28 00:38:59.945643–00:39:05.948186 UTC, including login, equality checks and warmups. Raw selected rows are in `raw/part3/attempts/20260928T003859.945761Z-cd277c20/requests.jsonl`; preflight, warmups and the complete manifest are adjacent. `benchmark_config.json` records the initial migration 001/index state, exact package versions, hardware, dataset checksum and source hashes.


Run: `20260928T003859.945761Z-cd277c20`  
Measured revision: `9860a20342072168ed68a8d41eb16d9bfecf7729`; dirty: `false`.  
Selected requests: **180** (30 per endpoint and page size).

Percentiles: R7 linear interpolation: rank=(n-1)*p, interpolate adjacent sorted values. All latencies are end-to-end HTTP milliseconds.

| Page size | Version | Requests | Total SQL/request (min–max) | Data SQL/request (min–max) | p50 ms | p95 ms | p99 ms |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | naive | 30 | 13–13 | 11–11 | 11.514 | 21.160 | 23.194 |
| 10 | fixed | 30 | 3–3 | 1–1 | 7.557 | 12.575 | 85.671 |
| 50 | naive | 30 | 53–53 | 51–51 | 26.380 | 42.758 | 53.385 |
| 50 | fixed | 30 | 3–3 | 1–1 | 8.630 | 12.088 | 15.529 |
| 200 | naive | 30 | 203–203 | 201–201 | 74.496 | 175.151 | 205.407 |
| 200 | fixed | 30 | 3–3 | 1–1 | 14.202 | 25.722 | 29.632 |

SQL counts come from response instrumentation, including authentication and session activity in the total. The JSON summary preserves every observed counter value and frequency.

| Page size | p50 speed-up | p95 speed-up | p99 speed-up |
| ---: | ---: | ---: | ---: |
| 10 | 1.524× | 1.683× | 0.271× |
| 50 | 3.057× | 3.537× | 3.438× |
| 200 | 5.245× | 6.809× | 6.932× |

Each speed-up divides the naive percentile by the corresponding fixed percentile. Values above 1 mean the fixed version was faster; values below 1 mean it was slower. These are ratios of percentiles, not percentiles of paired ratios.

With only 30 requests in each group, p95 and p99 depend strongly on the slowest observations. These observations do not establish performance outside this recorded environment.


The median latency improved from 11.514 to 7.557 ms at 10 rows, from 26.380 to 8.630 ms at 50 rows, and from 74.496 to 14.202 ms at 200 rows. The fixed version's median speed-up grew from 1.524× to 3.057× to 5.245×. Each larger naive page adds more database round trips; the join removes those trips. The fixed version still transfers and serializes more rows on larger pages, and both versions pay for HTTPS, authentication and activity updates. These shared costs limit the small-page benefit.

The result is not uniformly faster at every percentile. At size 10, fixed iteration 22 took 115.455 ms; the next-largest fixed observation was 12.753 ms. This outlier raised fixed p99 to 85.671 ms, versus 23.194 ms for naive, giving a p99 ratio of 0.271×. The available evidence cannot identify its cause; scheduling, connection or system noise are possibilities, not established explanations. We kept it in the selected first successful run. No samples were discarded or chosen to exaggerate speed-up.

`metrics.json` stores full-precision percentiles and observed SQL distributions; `summary_recomputed.json` independently checks all 18 percentile values, nine ratios, SQL ranges and the raw file hash. There were no failed HTTP measurement attempts in this session. Expected proof-first test failures and the deliberately refused repeat seed are preserved in `RUN_LOG.txt`, not mixed into the 180 rows.

## 3.8: Observed index behavior

An index is a separate ordered structure that helps MySQL locate matching rows. The existing manager foreign-key index is not a new index experiment. After all 180 timing requests finished, migration 003 added a new full-column index on listing title through the foundation migration runner:

```sql
CREATE INDEX ix_rentals_listing_title ON rentals (listing_title);
```

The committed migration checks the expected index definition so the shared runner can recover from an interrupted journal write without dropping data. The experiment itself refuses a preexisting title index; it cannot relabel an indexed state as before. Both observations used the exact same query and parameter:

```sql
SELECT id,listing_title FROM rentals WHERE listing_title=:title ORDER BY id;
-- title = 'HW4-6102-00001 Condo in Rose Garden'
```

Actual traditional EXPLAIN comparison:

| State | Access type | Chosen key | Estimated rows | Filtered % | Extra |
| --- | --- | --- | ---: | ---: | --- |
| Before | index | PRIMARY | 4868 | 10.0 | Using where |
| After | ref | ix_rentals_listing_title | 1 | 100.0 | Using index |

Before, MySQL chose a scan of the primary index and filtered rows by title. After, it could look up the equality value through the new title index. `Using index` reports that the index covers the selected columns. These are optimizer estimates, not measured rows read or a claimed index latency speed-up. The actual seeded table still contains 5,000 rows; the estimate 4,868 is not a changed row count. The N+1 speed-up table was measured before this index existed, so it must not be attributed to this later migration.

Actual query output was identical before and after:

```json
[
  {
    "id": 1,
    "listing_title": "HW4-6102-00001 Condo in Rose Garden"
  }
]
```

The normalized dataset checksum, physical-row checksum, result checksum and row counts all remained equal. Full traditional and JSON EXPLAIN, index inventories, journal entries and snapshots are preserved under `raw/part3/index/20260928T004453-df40d32d/`. Configuration records actual revision `62117550e2e2a253ea754152d2bb1007cc6b1f9a` and dirty=true because only evidence/prose files were pending; the executed code and migration were unchanged. An intentional repeat is retained separately at `raw/part3/index/20260928T004504-a87ff5a9/`, failed at preflight with `ddl_attempted: false`. A subsequent shared migration run reported none applied/already current.

## 3.9: Completed Postman evidence

All six required endpoint/size screenshots were captured in **Postman 12.29.5** against server revision `4f8390b84752d861ea6b47c5ac8615680192d841` at `https://localhost:8702`. Part 2 assigned an exclusive capture slot. The dedicated `s6102_rel` database at port 33363 still contained exactly 5,000 rentals and 200 managers, with migrations 001/003 and the listing-title index present. The [capture manifest](../raw/part3/postman/manifest.json) records timestamps, image hashes and configuration.

The unchanged [collection](postman_collection.json) ran one local functional iteration at **2026-09-28 01:53:31 UTC**: login followed by six GET requests. Postman reported **53 passed, 0 failed, 3 skipped and 0 errors**. All three fixed payloads equaled their naive counterpart; each earlier naive equality check was skipped until that counterpart was available. The [runner summary](../screenshots/part3/collection-run-summary.png), [size-200 equality screenshot](../screenshots/part3/payload-equality-200.png), and [runner text, top](../raw/part3/postman/runner-results-top.txt)/[bottom](../raw/part3/postman/runner-results-bottom.txt) preserve the results. The [configuration screenshot](../screenshots/part3/collection-run-configuration.png) shows one local functional iteration.

Each request below was then sent individually to capture its response. Its matching test image shows eight passing checks for status, JSON type, exact row count, ascending IDs, manager data and observed SQL headers. The equality check is skipped in these individual sends because its comparison values live only within one Collection Runner run; the completed run above supplies the equality evidence.

```http
GET https://localhost:8702/api/rentals/naive?page_size=10&offset=0
```

![Postman naive response, 10 rentals](../screenshots/part3/naive-10.png)

[Observed response headers](../screenshots/part3/naive-10-headers.png) show **13 total SQL statements**, including auth, and **11 data statements**. [Passing tests](../screenshots/part3/naive-10-tests.png) confirm exactly 10 rows and populated manager data.

```http
GET https://localhost:8702/api/rentals/fixed?page_size=10&offset=0
```

![Postman fixed response, 10 rentals](../screenshots/part3/fixed-10.png)

[Observed response headers](../screenshots/part3/fixed-10-headers.png) show **3 total SQL statements**, including auth, and **1 data statements**. [Passing tests](../screenshots/part3/fixed-10-tests.png) confirm exactly 10 rows and populated manager data.

```http
GET https://localhost:8702/api/rentals/naive?page_size=50&offset=0
```

![Postman naive response, 50 rentals](../screenshots/part3/naive-50.png)

[Observed response headers](../screenshots/part3/naive-50-headers.png) show **53 total SQL statements**, including auth, and **51 data statements**. [Passing tests](../screenshots/part3/naive-50-tests.png) confirm exactly 50 rows and populated manager data.

```http
GET https://localhost:8702/api/rentals/fixed?page_size=50&offset=0
```

![Postman fixed response, 50 rentals](../screenshots/part3/fixed-50.png)

[Observed response headers](../screenshots/part3/fixed-50-headers.png) show **3 total SQL statements**, including auth, and **1 data statements**. [Passing tests](../screenshots/part3/fixed-50-tests.png) confirm exactly 50 rows and populated manager data.

```http
GET https://localhost:8702/api/rentals/naive?page_size=200&offset=0
```

![Postman naive response, 200 rentals](../screenshots/part3/naive-200.png)

[Observed response headers](../screenshots/part3/naive-200-headers.png) show **203 total SQL statements**, including auth, and **201 data statements**. [Passing tests](../screenshots/part3/naive-200-tests.png) confirm exactly 200 rows and populated manager data.

```http
GET https://localhost:8702/api/rentals/fixed?page_size=200&offset=0
```

![Postman fixed response, 200 rentals](../screenshots/part3/fixed-200.png)

[Observed response headers](../screenshots/part3/fixed-200-headers.png) show **3 total SQL statements**, including auth, and **1 data statements**. [Passing tests](../screenshots/part3/fixed-200-tests.png) confirm exactly 200 rows and populated manager data.

[SSL verification remained enabled](../screenshots/part3/tls-verification.png), with the [custom public CA loaded](../screenshots/part3/tls-ca.png) with user assistance. Credentials stayed in unshared local values and were cleared afterward; the [clearing record](../raw/part3/postman/local-values-cleared.json) records UI verification at 2026-09-28 02:07:07.440 UTC. No credentials or cookie values are visible in these images. The [capture inventory and procedure](../screenshots/part3/README.md) links all 23 visually reviewed captures. The native tool emitted JPEG bytes; the exact [native originals](../raw/part3/postman/native-captures/) are retained, and the displayed PNGs are lossless conversions with identical decoded pixels and dimensions. No crop, resize, annotation or composite was applied ([format verification](../raw/part3/postman/image-format-check.json)).

These are functional screenshot requests after the index experiment. Their visible response times do not replace the selected 180-request dataset or its percentiles. The original timing rows, metrics, seed manifest, index snapshots and measured source bytes remain unchanged; [preservation evidence](../raw/part3/postman/preservation_after.json) and the [database postflight](../raw/part3/postman/postflight.json) record those checks. Place these real screenshots beside their matching requests and the §3.3/3.5 query code in the combined report.
