# Rental Housing Listings

A FastAPI application for managing rental listings, with cookie-based login and a protected dashboard. The repository also includes a local document-retrieval experiment and a LangGraph workflow for drafting and reviewing listing metadata.

## Features

- Create, edit, delete, and search rental listings by title or address.
- Log in and out with a server-managed session and a secure cookie.
- Compare token, semantic, and sentence-window chunking on a housing-document corpus.
- Draft listing metadata with a Planner–Reviewer graph, schema validation, and a configurable limit on revision turns.

The current HW4 web interface uses React, FastAPI and MySQL. Rental records and
login sessions persist across server restarts. Every rental endpoint requires a
valid login; the browser holds an opaque, HTTP-only cookie. The historical HW3
report remains unchanged and describes the earlier in-memory implementation.

## Run the HW4 application locally

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

[Foundation interfaces](reports/hw04/part2/FOUNDATION.md) and the
[shared contract](docs/plans/2026-09-27-1715-hw4-shared-contract.md) describe
how Parts 1–3 connect. [Part 2 evidence](reports/hw04/part2/REPORT_SECTION.md)
distinguishes passing checks from pending screenshots. Local integration is
tracked in [the partial write-up](reports/hw04/PARTS123.md); it is not a claim
that the entire homework is complete.

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
.venv/bin/python -m pytest tests/test_api.py tests/test_hw04*.py -q
.venv/bin/python scripts/hw04/part2/acceptance.py \
  --env-file /path/to/private/app.env --manage-server
```

The API acceptance script refuses an occupied port, restarts only its own server,
and cleans only its own test rows. Test fixtures use outer transactions and
savepoints; auto-increment values may still be consumed. Unconfigured real-DB
tests skip explicitly and do not count as MySQL proof. The partial integration
verifier is `scripts/verify_hw04_parts123.py`; its per-check outcomes remain
separate from final whole-homework verification.

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
  retrieval_compare.py   Retrieval experiment runner
  retrieval_summarize.py  Saved-result checks and summary tables
  agents_graph.py        Planner–Reviewer CLI
  agents_demo.py         Planner, Reviewer, and Finalizer demo
src/
  retrieval/             Chunking, indexing, scoring, and evaluation
  agent_graph/           Graph state, workers, and validation
  model_client.py        Shared local-model adapter
frontend/                React application (build output is ignored)
tests/                   API, browser, retrieval, and graph tests
scripts/                 Launch and verification tools
docs/                    Architecture and usage notes
reports/                 Reports, source snapshots, and recorded results
```

The [technical report](reports/hw03/report.pdf) covers authentication, session behavior, and the retrieval comparison. [Verification results](reports/hw03/verification.json) and the [run log](reports/hw03/RUN_LOG.txt) record the checks behind the published results.
