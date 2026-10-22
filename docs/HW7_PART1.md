# HW7 Part 1 setup and operation

Extend the shared semester application. Use Python 3.12, MySQL 8.0.16+ with
`s6102_rel`, the existing MongoDB `s6102_doc`, Ollama, and Node.js 22.12+.
Preserve existing databases and reports. Do not rerun homework data resets.

## Private configuration

Keep the virtual environment, secrets, TLS files, tokenizer, service logs, and
temporary captures outside the repository. Install `requirements-hw07.txt` or
the frozen `requirements-hw07.lock.txt` into a dedicated environment. The lock
also includes optional LangGraph/NumPy packages used for historical regression
tests. MCP and heavy retrieval tests use their existing separate environments.

Set `HW4_DATABASE_URL` to the existing MySQL SQLAlchemy connection URL and
`HW7_JWT_SECRET` to a cryptographically random secret of at least 32 bytes.
`HW7_JWT_TTL_SECONDS` defaults to 900 (allowed range 1–3600). No signing-key
fallback exists. Never pass passwords or signing secrets as CLI arguments.
The existing `HW6_*` model, MongoDB, tokenizer, and generation settings still apply.

For each role, set `HW7_READER_USERNAME`/`HW7_READER_PASSWORD`,
`HW7_WRITER_USERNAME`/`HW7_WRITER_PASSWORD`, and
`HW7_MODERATOR_USERNAME`/`HW7_MODERATOR_PASSWORD` in the private env file.
Usernames contain lowercase letters, numbers, and underscores, up to 64 characters.

```sh
python scripts/hw07/db_setup.py --env-file "$HW7_ENV_FILE" --seed-accounts
```

Run this against the integrated HW6 schema. Migration 005 adds unique usernames
and constrained roles. Existing users become `legacy_<id>` readers; IDs, names,
emails, and Argon2 hashes are retained. DDL steps are checked individually so a
partial migration can resume. A checksummed journal prevents editing an applied
migration. Repeat seeding preserves matching accounts and rejects collisions.
Existing session rows are retained as historical data and never authenticate requests.

Set `HW6_EXPERIMENT_USERNAME` and `HW6_DEMO_USERNAME` to the usernames of the
preserved HW6 accounts. Their passwords remain unchanged. HW6 CLI clients now
use the same bearer contract. The document verification command uses the
moderator variables because its acceptance sequence includes deletion.
Long-running HW6 HTTP clients renew shortly before expiry using their private
credentials. Renewal happens before an application request; failed renewal never
replays a chat or write. The `core` acceptance sequence uses one moderator
identity for document changes and restart checks.

## Run the integrated app

```sh
npm ci --prefix frontend
npm run build --prefix frontend
python scripts/run_hw06_web.py --env-file "$HW7_ENV_FILE" \
  --runtime-dir "$SHARED_RUNTIME_DIR" --cert "$TLS_CERT" --key "$TLS_KEY" \
  --events "$EXTERNAL_WORK_DIR/events.jsonl"
```

The runtime lease prevents competing local model/app experiments. The server
listens on `https://127.0.0.1:8702`. Trust the local certificate explicitly.

`POST /auth/login` accepts JSON `{"username":"...","password":"..."}` and returns
`access_token`, `token_type: "bearer"`, and `expires_in`. Send
`Authorization: Bearer <access_token>` to `GET /auth/me` and protected routes.
The token subject is the stable MySQL user ID. Verification fixes HS256, issuer,
audience, required claims, subject format, signature, and expiration. Every
request reads the current account and role from MySQL. Authentication failures
return 401 with a Bearer challenge; insufficient permissions return 403.

| Operation | reader | writer | moderator |
| --- | --- | --- | --- |
| List/read MySQL or document rentals | 200 | 200 | 200 |
| Create | 403 | 201 | 201 |
| Update | 403 | 200 | 200 |
| Delete | 403 | 403 | 204 |

Manager writes follow the same policy. `DELETE /api/rentals/highest` also requires
moderator. HW6 chat, memory, aggregate, and config require bearer authentication;
memory ownership checks still apply. No route requires an old session cookie.

The frontend stores its token in memory, calls the exact `/auth/*` paths, and
adds bearer headers to `/api/*` calls. Reload requires login. Logout clears the
local token and Redux data; a copied JWT remains usable until its 15-minute
expiry unless the account is removed. The backend always enforces permissions.

## Verification and lint

Use a private `HW4_TEST_DATABASE_URL` for transaction-rollback MySQL tests.
The focused suite is `pytest tests/test_hw07_auth.py tests/test_api.py
tests/test_hw05_api.py tests/test_hw06_documents.py tests/test_hw06_integration.py`.
The HW7 tests replace the old runtime cookie-auth tests; earlier evidence remains
in Git history. Injected HW6 service tests are labeled separately from live checks.
Client renewal tests use MockTransport and a controlled clock. Migration recovery
tests require `HW7_MIGRATION_TESTS=1` and an explicit
`HW7_MIGRATION_DATABASE_URL` for an isolated, DDL-capable test service. They create
and drop uniquely owned schemas and never reset the semester database. Keep test
administrator credentials separate from the application's restricted account.

Ruff 0.15.6 and pre-commit 4.5.1 are pinned. Ruff initially covers the shared web
backend, HW7 scripts, and HW7 Python tests. Historical reports and other homework
implementations are outside this lint rollout. Hook filters match that scope.

```sh
pre-commit install --allow-missing-config
ruff check .
ruff format --check .
pre-commit run --all-files
python scripts/hw07/part1_acceptance.py --env-file "$HW7_ENV_FILE" \
  --runtime-dir "$SHARED_RUNTIME_DIR" --work-dir "$FRESH_EXTERNAL_RUN_DIR" \
  --cert "$TLS_CERT" --key "$TLS_KEY" --output reports/hw07/raw/part1/acceptance.json
```

The live runner starts/stops only its owned server, exercises real storage and
Ollama, and cleans up only owned fixtures. Add `--browser-node "$NODE_BINARY"`
and make `playwright` resolvable through `NODE_PATH` for live Chromium acceptance.
Captures go under the external run directory. `scripts/hw07/log_command.py`
records commands, UTC timestamps, output and exit codes, redacting credentials.
Never put plaintext secrets or usable tokens in submitted evidence.

This is the Part 1 checkpoint. The final six-part verifier, report, and `hw7`
submission tag belong to later sessions.
