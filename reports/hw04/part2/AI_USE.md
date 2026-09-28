# AI use: Part 2

## 1. What you used an AI assistant for and what you did yourself

The user supplied the assignment, plans, shared contract, correct HW3 baseline, local-only shipping limits, and coordination requirements. Codex implemented the database models and migration, email/password authentication, persistent sessions, protected CRUD routes, HTTPS launcher, React-serving support, and automated checks. Codex also ran the available local checks, prepared this evidence fragment, and drafted the pending manual-capture instructions. Other Codex tasks own the React client and performance experiment. The report does not claim that the user personally wrote, ran, or manually verified this generated work. No AI model is used by the Part 2 application at runtime.

## 2. One AI-produced output that was wrong or unsuitable, or one thing independently verified

An AI-written database test expected every rejected rental value to raise SQLAlchemy `IntegrityError`. That expectation was too narrow for the actual MySQL/PyMySQL combination. Four tests failed because MySQL CHECK constraint error `3819` was exposed as `OperationalError`, even though the database correctly rejected the invalid rows. The initial result is preserved in `reports/hw04/raw/part2/pytest-backend-attempt1.txt`.

## 3. How the problem was detected or the result was verified

The tests were executed against real MySQL 8.4.11 rather than substituting SQLite. The initial selected run reported 110 passed and four failed. Its tracebacks showed error `3819` for the expected CHECK violations. The test also compared the stored rental IDs before and after rollback, so the check covered the database state as well as the exception. Separately, the HTTPS acceptance harness checked all five CRUD operations, login persistence and rental persistence across an actual server-process restart, logout revocation, and both expiry conditions; all 23 checks passed on the successful run.

## 4. What changed and why it works now

The constraint test now catches the shared SQLAlchemy `DBAPIError` base class and requires MySQL error `1048` for a NOT NULL failure or `3819` for a CHECK failure. It still rolls back and requires the same stored rows afterward. This tests the intended database behavior while respecting the driver's actual exception mapping. The final selected run passed 122 tests with no skips and 98 dependency deprecation warnings in 4.31 seconds. Its output is saved in `reports/hw04/raw/part2/pytest-backend.txt`. The larger total includes eight unchanged HW3 aggregate-verifier tests added to the selected run. Required manual screenshots and final Parts 1–3 integration remain separately pending.
