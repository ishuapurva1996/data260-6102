# HW4 Part 3 — Measured N+1 queries and a listing-title index

SID4 **6102**; PORT_BASE **8702**; PREFIX **s6102**; SEED **6102**; VERIFY_SEED **266102**; DOMAIN_ID **6**, Rental Housing Listings. Hardware: Apple M4, 10 CPU cores, 24 GiB memory. MySQL 8.4.11 runs in a dedicated Docker instance; Python 3.13.5 runs the shared FastAPI service. No language model is used by this performance experiment. This is a Part 3 fragment; Part 4, the complete PDF and the final hw4 submission tag are outside its scope.

## 3.1–3.2: Reproducible related data

A rental is one row describing a listing. Its `manager_id` refers to one property-manager row. Several rentals can share that manager; this is a many-to-one relationship. The foundation owns both tables and the foreign key in `code/web_application/migrations/001_initial.sql`, imported through commit `f29e7cc85baf52bea30bd4bb3209d1bd79b22051`.

The generator uses a local random-number generator with seed6102, shuffles 25 copies of manager ordinals1–200, and creates 5,000 valid six-field rental records. A unique listing title supports the later selective index query. IDs are assigned by MySQL.

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

The generated and stored checksums match after reloading the ORM objects. All200 managers have exactly25 rentals. Seeding checks the external ownership manifest, live MySQL UUID and Docker port before writing. It refuses existing rentals/managers and does not alter auth records. A real repeat invocation was refused without reseeding; the expected refusal is retained in `RUN_LOG.txt`.

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

Real HTTPS development smoke checks on auxiliary port8733 returned equal full payloads at all three sizes. These checks are separate from the final8702 latency dataset. Example actual response row:

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

The real-MySQL test additionally set nine page rows to the same manager and one to null under a transaction, then rolled back. The naive version still made11 data statements; the join made1. Concurrent requests retained independent counts.

## 3.4 and 3.6: Measurement method and raw evidence

Authentication loads the session/user and updates last activity. Those statements belong to the request cost. The counter starts before dependencies, observes SQLAlchemy cursor executions, and returns totals after JSON serialization. Data statements are tagged separately; reported counts are observed, not calculated from page size.

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

The runner logs in outside measurement, validates full naive/fixed equality for10,50,200 rows, and performs three warmups per group. It then records30 serial requests per endpoint/size, alternating naive then fixed for each iteration: exactly180 selected rows. A monotonic timer surrounds each buffered HTTPS request; JSON validation happens afterward. Every measured response must still equal its preflight baseline. Raw files include run ID, UTC timestamp, actual code revision/dirty state, configuration hash, status, row count, elapsed milliseconds and observed total/data SQL. Failed attempts are never combined with the successful run.

Percentiles sort the30 timings and use R7 linear interpolation at rank `(n−1) × p`. p50 is the middle of the observations. p95 and p99 describe the slow tail; at only30 samples, they depend strongly on the slowest few requests. The experiment uses warm caches and one worker without reload. Parts1/2 coordinated a quiet slot; unrelated pre-existing services were preserved, so incidental system noise remains possible.

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

