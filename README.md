# Rental Housing Listings

A React and FastAPI application for managing rental listings, with MySQL persistence and JWT bearer login. HW6 adds MongoDB documents and conversation memory; HW7 Part 1 adds reader, writer, and moderator permissions.

## Homework 7 Part 1

Use the [current setup and authentication guide](docs/HW7_PART1.md). It covers the
additive user migration, private signing key, role accounts, frontend build,
tests, Ruff, and live acceptance on HTTPS port 8702. The current API uses
`POST /auth/login` with username/password and `GET /auth/me`. All domain and HW6
memory routes use a bearer token. Earlier cookie authentication exists only in
Git history; historical reports and database rows are preserved.

The [Part 1 checkpoint](reports/hw07/PART1.md) distinguishes live checks from
automated tests. Parts 2–6, the final PDF, and the submission tag are pending.

## Homework 5

The [final HW5 report](reports/hw05/Apurva_HW5.pdf) contains the labeled screenshots,
results, reflection, and AI-use statement. An [editable Word copy](reports/hw05/Apurva_HW5.docx),
[reflection](reports/hw05/REFLECTION.md), and [AI-use answers](reports/hw05/AI_USE.md)
are included.

| Part | Implementation and usage guide |
| --- | --- |
| 1 | [Rental and manager APIs, database migration, and Redux UI](docs/HW5_PART1.md) |
| 2 | [Meals and rental MCP servers](docs/HW5_PART2.md) |
| 3 | [Validation, retries, timeouts, and measured results](docs/HW5_PART3.md) |
| 4 | [Tool executor and offline tests](docs/HW5_PART4.md) |
| 5 | [Bounded local agent, safety rule, and run logs](docs/HW5_PART5.md) |

Run the eight offline checks in the configured HW5 Python environment:

```sh
python scripts/hw05/run_offline_tests.py
```

These checks need no database or model server. The part guides describe dependencies,
live setup, and the saved evidence under `reports/hw05/`. Earlier reports remain
historical records; the application instructions below describe the HW4 foundation.

## Earlier homework

The [79-page HW4 report](reports/hw04/report.pdf) and
[HW4 evidence guide](reports/hw04/README.md) preserve its original screenshots,
experiments, AI-use answers, and verification procedure. The upload copy,
[Apurva_HW4.pdf](reports/hw04/Apurva_HW4.pdf), contains the same bytes.

## Features

- Create, edit, delete, and search rental listings by title or address.
- Log in using a username and password, send a JWT bearer token, and clear it on logout.
- Compare naive and joined MySQL list queries at page sizes 10, 50, and 200.
- Compare No-RAG, Basic-RAG, and Context-RAG answers against five housing documents.
- Compare token, semantic, and sentence-window chunking on a housing-document corpus.
- Draft listing metadata with a Planner–Reviewer graph, schema validation, and a configurable limit on revision turns.

The shared web interface uses React, FastAPI and MySQL. Rental records persist
across restarts. The browser keeps its JWT in memory and requires a new login
after a reload. Readers can list/read; writers can also create/update;
moderators can also delete. Historical reports retain their original behavior.

## Historical HW4 application setup

These instructions document the HW4 foundation. For the current application,
follow [HW7 Part 1](docs/HW7_PART1.md), including its JWT configuration and migration.

Use Python 3.12, Node.js 22.12 or newer, and a dedicated MySQL 8 instance containing `s6102_rel`.
Keep your connection and teaching-account values outside tracked source; see
[database setup](docs/HW4_DATABASE.md) and [.env.hw04.example](.env.hw04.example).

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# Export HW4_DATABASE_URL and HW4_SEED_NAME/EMAIL/PASSWORD privately.
.venv/bin/python scripts/hw04/db_setup.py --migrate --seed-demo --seed-account
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python scripts/run_hw04_web.py --env-file /path/to/private/app.env
```

Open [the application](https://127.0.0.1:8702/) or [API documentation](https://127.0.0.1:8702/docs).
The launcher creates a local self-signed certificate without changing OS trust.
Accept the local certificate warning in your browser. Login uses the seeded
email/password; there is no hardcoded account or registration flow. Sessions
expire after 300 seconds idle or 3600 seconds total. Logout revokes the stored token.

The same HTTPS service serves `/`, `/login`, `/create`, `/update?id=N` and
`/delete?id=N`. Build before starting; a missing build returns an explicit 503
message. API errors stay JSON. Use one worker without reload for measurements.
Do not stop another task's server or reset its database. Slot ownership lives in
`HW4_coordination/part2.md` outside this checkout.

[Foundation interfaces](reports/hw04/part2/FOUNDATION.md) describe how Parts 1–3
connect. The [HW4 reproduction guide](reports/hw04/REPRODUCIBLE_RUN_INSTRUCTIONS.md)
covers the current package. Earlier part handoffs retain their original dates,
scope, and implementation history.

## HW4 RAG experiment

[`code/rag.py`](code/rag.py) runs the local pipeline implemented in `src/rag/`.
The selected experiment is
[`scored-20260928-04`](reports/hw04/raw/part4/scored-20260928-04/): six questions
under three configurations, plus four additional answers for the top-k sweep.
All configurations use `qwen2.5:3b` for final answers; Context-RAG also uses
`qwen2.5:7b` to check whether a question needs clarification. The five-document
corpus and pinned configuration are included. Reported failures remain in the
saved results.

See the [reproduction guide](reports/hw04/REPRODUCIBLE_RUN_INSTRUCTIONS.md) for
offline evidence checks and commands for a separate new experiment. Model
downloads and a new run are not needed to inspect the submitted results.

## Compare document retrieval methods

The retrieval pipeline uses a local MiniLM embedding model to turn questions and document passages into 384-dimensional vectors. It compares three ways to split documents:

| Method | How it forms passages |
| --- | --- |
| Token | Splits text into chunks based on token count |
| Semantic | Groups text using changes in embedding similarity |
| Sentence window | Retrieves a sentence and includes neighboring sentences as context |

Each method uses its own in-memory vector index. The saved experiment asks five questions, retrieves the top three hits for each method, and records similarity scores, search timings, and whether the returned text supports the expected answer. The pipeline retrieves passages without generating answers.

Use a separate environment for the retrieval dependencies:

```bash
python3.12 -m venv .venv-retrieval
.venv-retrieval/bin/python -m pip install -r requirements-retrieval.txt
.venv-retrieval/bin/python code/retrieval_compare.py download-model
```

The download command caches the pinned model revision locally. Later retrieval runs load it from that cache and run on the CPU.

To check the saved results without downloading a model or repeating the experiment:

```bash
python3 code/retrieval_summarize.py \
  --run-dir reports/hw03/raw/part2/manual-screenshots-20260921 --check
```

The saved results contain answer-support labels based on the returned passages. A high similarity score alone does not establish that a passage contains the answer.

See the [retrieval guide](reports/hw03/part2/REPRODUCIBLE_RUN_INSTRUCTIONS.md) to run a new experiment, and the [measured results](reports/hw03/METRICS.md), [source documents](reports/hw03/SOURCES.md), and [questions](reports/hw03/questions.yaml) for the recorded comparison.

## Run the Planner–Reviewer workflow

The LangGraph workflow drafts listing metadata, reviews it, and requests revisions within a configurable worker-turn limit. Pydantic validates the Planner output. Model requests use the shared adapter in `src/model_client.py`.

Install [Ollama](https://ollama.com/) and start its local service, then prepare the model and a separate Python environment:

```bash
ollama pull qwen3:1.7b
python3.12 -m venv .venv-agents
.venv-agents/bin/python -m pip install -r requirements-agents.txt
.venv-agents/bin/python code/agents_graph.py \
  --input-json reports/hw02/cases/part3_listing.json
```

See the [graph architecture and usage guide](docs/agent_graph.md) for response validation, turn counting, and test commands. The [model experiments](reports/hw02/METRICS.md) record how the turn limit affects completion and retries.

## Tests and verification

Current HW4 tests use real MySQL when `HW4_TEST_DATABASE_URL` is explicitly set.
Run them against a dedicated test instance, never concurrently with benchmarks:

```sh
.venv/bin/pytest tests/test_api.py tests/test_hw04*.py -q
.venv/bin/python scripts/hw04/part2/acceptance.py \
  --env-file /path/to/private/app.env --manage-server
```

The API acceptance script refuses an occupied port, restarts only its own server,
and cleans only its own test rows. Test fixtures use outer transactions and
savepoints; auto-increment values may still be consumed. Unconfigured real-DB
tests skip explicitly and do not count as MySQL proof. The partial integration
verifier is `scripts/verify_hw04_parts123.py`. The whole-homework verifier is
`scripts/verify_hw04_submission.py`: `--prepare` checks saved evidence offline;
`--tagged` checks the exact `hw4` checkout and runs an HTTPS smoke test using two
explicit private environment files. See the
[verification instructions](reports/hw04/REPRODUCIBLE_RUN_INSTRUCTIONS.md#submission-verification)
before running either mode.

After building React, the repeatable browser run checks CRUD, restart persistence,
logout and controlled idle expiry. Preserve the original branch evidence by using
separate output directories:

```sh
.venv/bin/python tests/browser_hw04_part1_runtime.py \
  --env-file /path/to/private/app.env --node node \
  --raw-dir reports/hw04/raw/part2/integrated-browser \
  --screenshots-dir reports/hw04/screenshots/part2/integrated-browser
.venv/bin/python scripts/hw04/part2/integration_smoke.py \
  --env-file /path/to/private/performance.env
```

Run these sequentially on the reserved port 8702. The second command requires
Part 3's existing 5,000-rental/200-manager dataset; it verifies built assets,
deep links, shared authentication, equivalent payloads and measured SQL counts.
It does not seed or reset data. See [Part 3 instructions](scripts/hw04/part3/README.md)
for ownership checks and the explicit `HW4_PART3_MYSQL_TESTS=1` opt-in required by
its live pytest cases. `HW4_TEST_DATABASE_URL` can independently point ordinary
CRUD fixtures at a separate test instance.

Historical HW3 reports and verifier scripts are preserved for reference. Their
old public-API/signed-cookie/Jinja expectations do not describe the current app;
do not regenerate their evidence from HW4. Retrieval and agent source remain
unchanged, and their separate environments still apply.

## Repository layout

```text
code/
  web_application/       MySQL models, authenticated FastAPI routes and React serving
  rag.py                 HW4 local RAG experiment CLI
  retrieval_compare.py   Retrieval experiment runner
  retrieval_summarize.py  Saved-result checks and summary tables
  agents_graph.py        Planner–Reviewer CLI
  agents_demo.py         Planner, Reviewer, and Finalizer demo
src/
  rag/                   HW4 retrieval, context construction, generation and evaluation
  retrieval/             Chunking, indexing, scoring, and evaluation
  agent_graph/           Graph state, workers, and validation
  model_client.py        Shared local-model adapter
frontend/                React application (build output is ignored)
tests/                   API, browser, retrieval, and graph tests
scripts/                 Launch and verification tools
docs/                    Architecture and usage notes
reports/                 Reports, source snapshots, and recorded results
```

The [HW4 report](reports/hw04/report.pdf), [metrics](reports/hw04/METRICS.md),
[run log](reports/hw04/RUN_LOG.txt), and [AI-use answers](reports/hw04/AI_USE.md)
form the previous HW4 submission. The [HW3 report](reports/hw03/report.pdf),
[HW3 verification](reports/hw03/verification.json), and earlier homework tags
preserve the previous implementations and their results.

# HW6 foundation

The shared HW6 contracts and runtime setup are described in
[HW6_FOUNDATION.md](docs/HW6_FOUNDATION.md). The four homework parts and integrated
routes extend the existing FastAPI factory. File memory stays a separate CLI.
Launch the integrated service with external configuration and TLS:

```sh
python scripts/run_hw06_web.py --env-file /private/sql.env --env-file /private/hw06.env \
  --runtime-dir /private/runtime --cert /private/cert.pem --key /private/key.pem \
  --events /private/runtime/events.jsonl
```

The launcher holds the shared runtime lease and binds HTTPS port 8702. Existing
login protects the document, chat, inspection, aggregate and configuration APIs.
The objective smoke command starts its own leased instance, so stop an instance
you own before using it:

```sh
python scripts/verify_hw06.py --env-file /private/sql.env --env-file /private/hw06.env \
  --runtime-dir /private/runtime --cert /private/cert.pem --key /private/key.pem \
  --work-dir /private/fresh-smoke-directory
```

It writes reports/hw06/verification.json, uses disposable namespaced records, and
checks the declared application/experiment source hash before and after. Source
must be committed first. Real acceptance and a single unscored N30 pilot use
scripts/hw06/acceptance.py with the same arguments and --stage core, file,
comparison, or pilot. These acceptance runs are separate from the four-condition
measurement command documented in scripts/hw06/part3/README.md.
