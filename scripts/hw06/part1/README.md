# Part 1: MongoDB rental documents

`DocumentService(database, *, clock=utc_now)` uses the exact `Database` object
from A's `MongoConnection`. It owns only `s6102_doc.rentals` and never closes the
shared client. Construction does no network work. `prepare_collection()` creates
the collection or applies its validator with `collMod`, lazily on first use or
explicitly at startup. It never deletes or rewrites existing data. Existing
invalid records require a separate audit; `collMod` does not repair them.

This is a document representation of rental listings. It does **not** synchronize
with MySQL `s6102_rel`, and the existing SQL `/api/rentals` API keeps its meaning.
Only authenticated users may access these routes, using existing `require_user`.
As with the existing rental API, the collection is shared among authenticated
users; it is not personal chat memory.

## API contract

| Field | Input and storage rule |
| --- | --- |
| `listingTitle` | Required string, trimmed first, then 1–100 characters |
| `description` | Optional string or null; maximum 5,000 characters |
| `status` | `available` (default), `reserved`, `rented` |
| `propertyType` | Required: `apartment`, `house`, `condo`, `townhouse` |
| `availableFrom` | Required ISO 8601 timestamp: `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` or an explicit `±HH:MM` offset |
| `id` | Response-only lowercase 24-character hexadecimal ObjectId; stored as BSON `_id` |
| `created_at`, `updated_at` | Response-only, server assigned UTC timestamps |

Date-only strings, naive timestamps, epoch numbers and booleans are rejected.
Input dates normalize to UTC. BSON stores dates to milliseconds, so dates and
server timestamps truncate finer precision before writing; JSON uses ISO 8601
with `Z`. An immediate update within the same millisecond may have the same
`updated_at`; it is a wall-clock timestamp rather than a version counter.
Unknown fields, including client-supplied IDs and timestamps, are rejected.

PUT is a full replacement of user fields: all required fields must be supplied;
omitted `status` becomes `available`, and omitted `description` becomes null.
`_id` and `created_at` are preserved atomically, and `updated_at` is server set.
The stored MongoDB validator separately checks BSON types, required fields,
trimmed nonblank title/length, description length and categorical values. Direct
MongoDB writes must supply timestamps/status; server defaults are API behavior.
A collection validator cannot enforce that a direct writer preserves historical
`created_at`; use the API for managed updates.

| Route under `/api/doc-rentals` | Success |
| --- | --- |
| POST | 201, saved document |
| GET | 200, all documents ordered by `(created_at, _id)` |
| GET `/{id}` | 200, one document |
| PUT `/{id}` | 200, replaced document |
| DELETE `/{id}` | 204, empty response |

Invalid body/JSON and malformed IDs return 422; missing records return 404;
missing authentication uses the existing 401. Driver/storage failures return
sanitized 503 `storage_unavailable`. MongoDB validation error 121 returns 422
`document_validation_failed`. Unexpected service failures return sanitized 500
`internal_error`. Logs keep operation/error-code/type, without private driver
messages or credentials. List failure never returns a partial successful list.

## Integration in A's existing application

A must mount the router; B does not change `main.py` or start a second server:

```python
from src.hw06_documents.service import DocumentService
from web_application.routers.doc_rentals import create_router
from src.hw06_shared.errors import install_error_handlers

# connection is A's single MongoConnection, also used by Part 2.
service = DocumentService(connection.database)
install_error_handlers(app)
app.include_router(create_router(service))
```

A also configures shared `CORSMiddleware` for `HW6Config.cors_origins`, including
credential handling for the existing login cookie, and retains the sanitized
`RequestValidationError` handler. CORS is absent from the foundation `main.py`;
this is an integration obligation. FastAPI already parses JSON request bodies
into `RentalCreate`/`RentalUpdate`; no separate JSON-parsing server is needed.
A retains shutdown ownership of the shared connection and reruns final combined
app acceptance, including the existing SQL API and authentication.

## Focused offline checks

Use the frozen A-owned Python environment; do not install into it:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:code /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime/venv/bin/python -m pytest tests/test_hw06_documents.py tests/test_hw06_documents_edges.py -q -p no:cacheprovider
```

These exercise actual Pydantic schemas, service and router in process against
isolated BSON-roundtripping fixtures. They do not establish real MongoDB
validator enforcement, HTTPS/login, CORS or integrated app readiness.

## Real acceptance and capture

A must first make shared MongoDB reachable, restore existing SQL/login, mount
the router and handlers, configure CORS, and launch the **existing** HTTPS app
on 8702 with the final source revision. Keep credentials/cookies outside Git.
The command below acquires A's `RuntimeLease` itself; do not wrap it in a second
lease. A's `/api/hw06/config` endpoint must be mounted for full capture.

1. Obtain a valid private Netscape cookie jar through the existing HTTPS login.
   Record no cookie or password in submitted evidence.
2. From the integrated checkout, run the capture. Replace the private cookie path
   and use a fresh external output directory for every attempt:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:code /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime/venv/bin/python -m scripts.hw06.part1.verify \
  --env-file /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime/hw06.env \
  --runtime-dir /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime \
  --base-url https://localhost:8702 \
  --ca-file /Users/pragyaapurva/code/agent_outputs/data260-hw5/sessions/integration/runtime/cert.pem \
  --cookie-file /absolute/private/login-cookies.txt \
  --output-dir /Users/pragyaapurva/code/agent_outputs/data260-hw6/part1-live-final-01 \
  --keep-sample
```

Use `--probe-only` without cookies to check only availability. Exit 2 means a
runtime/storage gate blocked progress; exit 1 means acceptance failed; exit 0
with `status=passed` means full checks passed. `status=availability_only` is
strictly a probe, not CRUD acceptance. Every attempt records UTC timestamps,
local source commit/hashes and sanitized configuration. Full capture also saves
server configuration, actual HTTP requests/responses and latency, validation
examples for POST and PUT, stored BSON sample/options and direct invalid BSON
rejections. Check that the recorded server revision agrees with the integrated
checkout. Never promote a mismatched run as final-revision evidence.

3. Save readable real client screenshots for POST, list GET, detail GET, PUT,
   DELETE and representative 422 responses. Pair each output with the short
   matching source excerpt. Show `Pragya Apurva` in every terminal screenshot.
4. `--keep-sample` leaves exactly one newly created synthetic sample after the
   CRUD fixture is deleted. Its ID and exact cleanup route appear under
   `sample_for_capture` in `verification.json`. In Compass, connect using A's
   shared connection, select `s6102_doc` → `rentals`, and filter by that `_id`.
   Alternatively, use mongosh with that same connection/database and run:

```javascript
print("Pragya Apurva | HW6 Part 1");
printjson(db.getSiblingDB("s6102_doc").rentals.findOne({_id: ObjectId("COPY_CAPTURED_SAMPLE_ID")}));
printjson(db.getSiblingDB("s6102_doc").getCollectionInfos({name: "rentals"})[0].options);
```

5. Capture the real Compass/mongosh view with fields visible, then use the
   recorded authenticated DELETE route for that exact sample ID (expect 204,
   then GET 404). Preserve the deletion responses. Never drop the database,
   collection, or delete unrelated documents. The tool cleans up its other
   fixture IDs even after a later assertion fails.
6. A promotes selected real outputs/screenshots into `reports/hw06/raw/part1/`
   and reruns final combined-app acceptance on the integrated revision. CORS
   acceptance must include a credentialed preflight from an allowed configured
   origin: `OPTIONS /api/doc-rentals` with `Origin`,
   `Access-Control-Request-Method: POST`, and
   `Access-Control-Request-Headers: content-type`. Check the exact allowed
   origin and `Access-Control-Allow-Credentials: true`; reject a disallowed
   origin. Then check the actual authenticated JSON POST response headers.

MongoDB references: [stored JSON Schema validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/),
[collection creation options](https://www.mongodb.com/docs/manual/reference/method/db.createcollection/).
