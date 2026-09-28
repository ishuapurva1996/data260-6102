---
title: "feat: HW4 Part 2 MySQL authentication and CRUD"
date: 2026-09-27
type: feat
artifact_contract: ce-unified-plan/v1
product_contract_source: course-assignment
execution: code
---

# HW4 Part 2: MySQL persistence and server-side sessions

## Goal Capsule

**Objective:** Authenticated users can manage persistent rental records, and Parts 1 and 3 can use one working database-backed service.

**Means:** Extend the existing FastAPI app with MySQL, SQLAlchemy and server-side login sessions under the [shared contract](2026-09-27-1715-hw4-shared-contract.md).

**Authority:** User instructions and HW4 PDF → shared contract → this plan. This session owns Part 2, the early foundation handoff and local integration of Parts 1–3. Commit locally; no publishing, deployment or final homework tagging.

---

## Product Contract

### Summary

Replace the process-memory rental and session stores with MySQL, enforce authentication on record operations and provide a stable API to the other sessions.

### Problem Frame

HW3 loses rental data at process restart and uses a demonstration credential with an in-memory session registry. Its rental API remains public. HW4 requires persistent records, email/password login, opaque cookie tokens and database session rows.

### Requirements

| ID | Required result | Assignment source |
| --- | --- | --- |
| R1 | Extend the same FastAPI service and domain; use `s6102_rel` and connection variable `db_session_basede26`. | Part 2 / general instructions |
| R2 | Store rentals with auto-increment IDs and validated domain fields; implement POST, list GET, ID GET, PUT and DELETE. | Part 2 CRUD |
| R3 | Store users with unique email and password_hash; validate email/password login. | Parts 1–2 authentication |
| R4 | Store opaque sessions in MySQL and reference them only through an HTTP-only browser cookie; reject unauthorized record access. | Parts 1–2 sessions |
| R5 | Prove persistence, logout revocation and expiry behavior with real database tests. | Required behavior and preserved HW3 session lifecycle |
| R6 | Provide Postman screenshots for all five CRUD operations plus database and project-structure screenshots. | Part 2 evidence |
| R7 | Publish the common foundation early and integrate Parts 1–3 with objective partial verification. | Parallel execution agreement |

### Scope Boundaries

Own shared models/migrations/auth/core wiring. Include the small related-table schema needed by Part 3, but leave generator, performance queries and indexing experiment to that session. Leave React UI implementation to Part 1. No user-registration product, cloud deployment or Part 4 implementation is requested.

---

## Planning Contract

### Key Technical Decisions

- KTD1. Keep the existing service entry point and launch/import compatibility. Add database, schema, CRUD and authentication modules inside `code/web_application/`; document imports so the performance module works under both the launcher and tests.
- KTD2. Use SQLAlchemy 2.x with a compatible MySQL driver and explicit versioned migrations. Pin compatible dependencies during execution rather than upgrading the unrelated retrieval/agent environment.
- KTD3. Preserve the six-field create contract and two-field update contract in the shared agreement. MySQL generates IDs; deleting the highest ID must not manually reset the sequence.
- KTD4. Use one database-backed authentication system. Retire active acceptance of HW3 signed user-data cookies and process-local session records. Preserve idle/absolute expiry semantics through shared-contract fields and checks.
- KTD5. Publish foundation B once the core MySQL/auth/API smoke test passes. Its models include the agreed manager relation, so Part 3 does not need competing base migrations.
- KTD6. Serve Part 1's built React assets through the same HTTPS service. Explicit frontend routes replace the Jinja route ownership without swallowing API errors.

### Dependencies and risks

U1–U3 can run immediately. U4's UI verification depends on Part 1, and U5 depends on both completed branches. MySQL/container/runtime availability and local account provisioning are execution checks, not assumed successes. If blocked by a missing runtime, finish all unaffected code/docs/tests and identify the exact missing dependency; never substitute SQLite for required MySQL proof.

Do not reset any existing database or stop a process merely because it uses the desired port. Use dedicated development instances and coordinate final port 8702 evidence as specified in the shared agreement.

---

## Implementation Units

### U1. Establish database configuration and reproducible schema

**Goal:** A real MySQL database contains the shared schema. **Requirements:** R1, R2, R7. **Dependencies:** Shared contract.

**Files:** `code/web_application/database.py`, `models.py`, configuration/schema modules, `code/web_application/migrations/001_*`, local configuration example without secrets, `requirements.txt`, database setup documentation, `tests/test_hw04_database.py`.

**Approach:** Create engine/session lifecycle around `db_session_basede26`, all four agreed models and a repeatable migration path. Preserve the backend's import constraints. Keep credentials outside tracked files and make seeds explicit. Configure request-scoped sessions and transaction rollback/closure.

**Test scenarios:**
- An empty dedicated MySQL instance obtains the expected schema and foreign keys; repeat setup preserves existing rows.
- IDs auto-increment; unique email and required-field constraints are enforced.
- A committed rental remains after restarting the service; an invalid write rolls back without partial data.

**Verification:** Inspect actual MySQL rows and schema; record engine version and setup command. Do not claim an unobserved import of live HW3 memory data.

### U2. Implement email login and persistent sessions

**Goal:** Only a valid active login authorizes rental access. **Requirements:** R3–R5. **Dependencies:** U1.

**Files:** `code/web_application/routers/auth.py`, session/auth helpers, `session_store.py` as needed for retirement, `main.py`, teaching-account seed script, `tests/test_hw04_auth.py`.

**Approach:** Hash passwords using a maintained library, seed a configurable teaching account, and implement login/me/logout plus a shared session dependency. Set the exact cookie contract. Check absolute and idle expiry using UTC times, update activity consistently, and revoke the token on logout. Keep secrets out of output and evidence. No user data belongs inside the cookie.

**Test scenarios:**
- Correct credentials authenticate; wrong password/unknown email return 401 without a session.
- Cookie attributes are correct; token lookup resolves the stored user and session expiry.
- Logout, expired sessions and forged/old HW3 cookies cannot authorize an API request.
- Missing/expired cookies fail on each ordinary rental route; a valid database session works after process restart while still within its lifetime.

**Verification:** Real API/database checks prove the lifecycle. Capture cookie attributes without exposing reusable token values.

### U3. Move ordinary CRUD to MySQL and release foundation B

**Goal:** Other sessions can integrate against a stable backend. **Requirements:** R1, R2, R4, R7. **Dependencies:** U1, U2.

**Files:** `code/web_application/main.py`, rental schemas/CRUD/router modules, `scripts/run_hw04_web.py`, minimal React-serving wiring, `tests/test_api.py`, `tests/test_hw04_crud.py`, `tests/test_hw04_serving.py`, `reports/hw04/part2/FOUNDATION.md`.

**Approach:** Replace the in-memory store and protect all old and new rental paths. Preserve search and delete-highest with safe literal-route ordering. Add ID GET. Return the agreed status codes and response shapes. Adapt tests whose old expectations intentionally change; do not weaken validation to avoid failures. Expose the agreed engine, session dependency, models and auth dependency to Part 3 in FOUNDATION.md. Include the HW4 HTTPS launcher and minimal frontend asset/deep-link serving in B, with an explicit missing-build state. Part 1 must be able to import B and serve its own completed frontend build without waiting for U4.

**Test scenarios:**
- Authenticated create/list/ID lookup/update/delete obey the exact body and response contracts.
- Invalid fields return 422, unknown IDs return 404, unauthenticated calls return 401 and no data changes.
- Updating two fields preserves the other four; concurrent creates get distinct database IDs.
- Search and highest-ID deletion remain correct and protected.

**Verification:** Commit the working foundation, publish its exact hash and tested MySQL setup to the shared handoff immediately, and keep API/model changes coordinated afterward. Foundation completion must not wait for React or benchmarking.

### U4. Integrate frontend serving and collect Part 2 evidence

**Goal:** The service supports React deep links and demonstrates all required backend operations. **Requirements:** R5–R7. **Dependencies:** U3; Part 1 build for final UI verification.

**Files:** `code/web_application/main.py`, old template-routing compatibility code, `scripts/run_hw04_web.py`, launcher/readme updates, `tests/test_hw04_serving.py`, `reports/hw04/part2/` and Part 2 raw/screenshots directories.

**Approach:** Verify the launcher and serving plumbing already published in U3 against Part 1's real build. Confirm `frontend/dist` assets and explicit browser routes work while API/docs retain priority. Make any necessary fixes available as an additional committed handoff before Part 1 finishes its evidence. Create a Postman collection with login and all five CRUD requests; use actual API responses and database screenshots for the report fragment.

**Test scenarios:**
- Direct visits to `/`, `/login`, `/create`, `/update?id=N`, `/delete?id=N` work after a real build.
- An unknown `/api` endpoint returns a 404 API response, not index.html.
- Each Postman CRUD operation changes or reads the expected MySQL row, with authentication enforced.

**Verification:** Capture real Postman responses, database contents and project structure. Record checks, timestamps, code snippets and AI_USE answers; list inaccessible UI captures as pending.

### U5. Combine Parts 1–3 and verify the integrated application

**Goal:** All three branches work together in one application. **Requirements:** R7 and the shared integration agreement. **Dependencies:** U4 and completed Part 1/Part 3 handoffs.

**Files:** Shared wiring/conflict resolutions, `scripts/verify_hw04_parts123.py`, `reports/hw04/verification.parts123.json`, root HW4 log/metrics/AI-use/partial write-up, `reports/hw04/part2/HANDOFF.md`, relevant integration tests.

**Approach:** Merge completed branches while preserving shared foundation ancestry. Build the UI and run the saved API/browser/performance checks against the merged tree. The per-branch port-8702 acceptance slots occur before this final merge, as the shared contract specifies. After merging, coordinate any integrated reruns on 8702, combine part fragments without losing provenance, and rerun the full selected benchmark if integrated behavior changed. Prepare a source-read-only partial verifier and document the later full-homework verification requirement.

**Test scenarios:**
- UI mutations, normal CRUD and both performance endpoints use the same auth and schema.
- All six performance combinations return equivalent data; recorded measurements identify the code actually measured.
- The partial verifier writes configuration, commit, seeds and individual pass/fail checks without editing application source.

**Verification:** Publish integrated branch/hash and reproducible run instructions. If another session is unfinished, publish the exact integration dependency and continue once its handoff arrives; do not label integration complete early.

---

## Verification Contract

Use real MySQL integration tests for schema, CRUD and authentication; exercise expiry with controlled time rather than long sleeps. Run the relevant Python checks, the Part 1 browser runner, and Part 3 equivalence/query-count smoke checks after integration. Update superseded test expectations explicitly; never rerun old report regeneration commands or replace their saved artifacts.

The final Parts 1–3 handoff distinguishes implementation, automated verification and missing manual evidence. It names the remaining whole-homework work: Part 4, final PDF/AI_USE integration, collaborator access confirmation, `hw4` tag and tagged-commit `verification.json`.

## Definition of Done

R1–R7 hold, the foundation hash was published, and the merged local application is verified or a precise unfinished sibling dependency is stated. No credentials, reusable session tokens or generated environments are committed. All work remains in shared application folders. Part-specific and aggregate evidence retain actual timestamps and measured revisions. Remove abandoned code paths that would bypass the new authentication. Do not claim full HW4 completion or publish the repository.
