# Rental Housing Listings

A FastAPI application for managing rental listings, with cookie-based login and a protected dashboard. The repository also includes a local document-retrieval experiment and a LangGraph workflow for drafting and reviewing listing metadata.

## Features

- Create, edit, delete, and search rental listings by title or address.
- Log in and out with a server-managed session and a secure cookie.
- Compare token, semantic, and sentence-window chunking on a housing-document corpus.
- Draft listing metadata with a Planner–Reviewer graph, schema validation, and a configurable limit on revision turns.

The web interface uses Jinja templates and locally bundled Bootstrap 5.3.2. Listings and sessions are stored in memory. Restarting the server restores the seed listings and ends active sessions. Run one server worker for this setup.

## Run the web application

Use Python 3.12 and run these commands from the repository root:

```bash
python3.12 -m venv .venv-web
.venv-web/bin/python -m pip install -r requirements.txt
.venv-web/bin/python scripts/run_hw03_web.py --prepare-cert
.venv-web/bin/python scripts/run_hw03_web.py --host ::1 --port 8702
```

Open [the application](https://[::1]:8702/) or [the API documentation](https://[::1]:8702/docs). The local certificate is self-signed, so the browser displays a certificate warning.

The demo login is `admin` / `password`. Sessions expire after 300 seconds of inactivity. Logging out revokes the session on the server. The session cookie uses `HttpOnly`, `Secure`, and `SameSite=lax`, so login requires HTTPS.

The dashboard requires login; the rental-listing API remains public. Stop the server with `Control-C` before starting another process on port 8702.

See the [web application guide](code/web_application/README.md) for routes, Docker usage, and browser checks, and the [domain schema](DOMAIN_SCHEMA.md) for listing fields.

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

Run the web and authentication tests:

```bash
.venv-web/bin/python -m pytest \
  tests/test_api.py tests/test_hw03_auth.py tests/test_hw03_integration.py
```

Run the retrieval tests:

```bash
.venv-retrieval/bin/python -m pytest tests/retrieval -q
```

With both environments installed, run the combined verifier:

```bash
python3 scripts/verify_hw03.py --require-report \
  --run-dir reports/hw03/raw/part2/manual-screenshots-20260921
```

The verifier checks the saved results, source versions, and report build hashes. It reruns the web/API tests and writes updated verification records under `reports/hw03/`. The [reproduction guide](reports/hw03/REPRODUCIBLE_RUN_INSTRUCTIONS.md) includes browser-test setup and an optional check using the cached embedding model.

## Repository layout

```text
code/
  web_application/       FastAPI app, templates, and static assets
  retrieval_compare.py   Retrieval experiment runner
  retrieval_summarize.py  Saved-result checks and summary tables
  agents_graph.py        Planner–Reviewer CLI
  agents_demo.py         Planner, Reviewer, and Finalizer demo
src/
  retrieval/             Chunking, indexing, scoring, and evaluation
  agent_graph/           Graph state, workers, and validation
  model_client.py        Shared local-model adapter
tests/                   API, browser, retrieval, and graph tests
scripts/                 Launch and verification tools
docs/                    Architecture and usage notes
reports/                 Reports, source snapshots, and recorded results
```

The [technical report](reports/hw03/report.pdf) covers authentication, session behavior, and the retrieval comparison. [Verification results](reports/hw03/verification.json) and the [run log](reports/hw03/RUN_LOG.txt) record the checks behind the published results.
