# HW7 Part 4: Capital Bikeshare framework agent

The existing authenticated application adds `/bikeshare`. Parts 2 and 3 remain hand-written. This feature uses LangGraph 1.0.8 `create_react_agent` v2 and `ToolNode`, with the shared `src/model_client.py` Ollama adapter. LangGraph owns tool dispatch and the reasoning/action loop. Its supported 1.x prebuilt API emits a deprecation warning; upgrading to the replacement API is a future dependency change.

## Compatible environment

Use Python 3.12 and a separate virtual environment. Install `requirements-hw07-part4.lock.txt`; `requirements-hw07-part4.txt` records direct compatibility constraints. The earlier web and MCP environments and their dependency files remain separate. `langgraph-prebuilt==1.0.7` matches graph 1.0.8; the older environment's prebuilt 1.0.13 import failure is why this feature has its own environment. Verify with `python -m pip check` and the framework tests before starting a server.

Start existing MySQL, MongoDB, and local Ollama services. Reuse private HW7 configuration containing the existing database URL, signing secret, and role credentials. Never put those values in Git or console captures.

```sh
python scripts/hw07/bike_web.py \
  --env-file /absolute/private/runtime.env \
  --runtime-dir /absolute/private/shared-runtime \
  --run-root /absolute/private/bike-runs \
  --events /absolute/private/hw6-events.jsonl \
  --cert /absolute/private/cert.pem --key /absolute/private/key.pem
```

This serves the shared React/FastAPI application over HTTPS on 127.0.0.1:8702, retaining HW6 document and memory routes. Build the existing frontend first with its Vite build command. The startup lease is released before serving jobs; every bike worker independently acquires the same shared model lease. Schedule other HW6 model experiments outside bike runs. An already-held lease produces an explicit busy failure, with no model request. No existing database reset, account reseed, or fixture cleanup is needed for bike comparisons.

## Input and account basis

The upload retains the thirteen original modern Capital Bikeshare trip columns and adds `scenario_account_id`, `coverage_start`, `coverage_end`, and `scenario_account_assumption`. All accounts need one common 30-day window, positive trips, and two minutes between rides on the same account. Include `source_csv`, `source_row_number`, and `source_csv_sha256` together for provenance. Original `member_casual` remains a source fact; it does not establish a scenario account's identity or purchased plan.

`reports/hw07/cases/bikeshare` contains two frozen, 500-row selections from the genuine January 2024 public CSV. Their appended account labels are explicit hypothetical assignments: ten accounts with fifty rides each, or 125 accounts with four rides each. Their window is January 1 through January 31, 2024, exclusive for new starts. These are counterfactual scenarios priced using newly captured policies, not observed personal histories or historical bills. A membership fee is charged separately to every account.

Reproduce and verify all original field values and deterministic selection from the official archive's CSV:

```sh
python scripts/hw07/bike_cases.py --help
python scripts/hw07/bike_cases.py --source /absolute/202401-capitalbikeshare-tripdata.csv --verify
```

The manifest records official source URL, archive/CSV hashes, original row numbers and value hashes, daily selection quotas, account assignment rules, and input hashes. The full public source archive need not be committed. Invalid uploads are rejected as a whole; no trip is silently dropped. Offset-free windows crossing a daylight-saving transition require explicit offsets and thirty elapsed days.

## Trust boundaries and costs

The three advertised schemas are `TOOL_SCHEMAS` in `src/bikeshare/tools.py`. Tool functions return the common `success/data/error/source/ts` envelope. They accept injected database, policy-fetch, and clock dependencies for independent tests.

- `csv_sql`: one SQLite-parsed SELECT, private in-memory `trips`, `query_only`, restrictive authorizer, approved functions, statement/time/instruction/row limits. Writes, multiple statements, other tables, files and side effects stay blocked in normal runs.
- `policy_retriever`: short exact-substring passages ranked for query relevance and charge rules. The run-local fetch/cache permits only official Capital Bikeshare HTTPS hosts, validates redirects before requests, and limits body size, capture count and time. Standard-library HTTPS is used because the help site challenged the tested HTTPX client. HTTP failures retain the response body and failure metadata; no remembered price replaces them.
- `calculator`: arithmetic whitelist plus a bounded AST interpreter. Names, function calls, powers, division by zero, nonfinite/oversized numbers and deep expressions fail. No `eval` is used.

The agent retrieves the entered pricing page and official single-trip and membership pages (the membership page also states rounding). Each capture saves exact UTF-8 text, HTML, UTC access time, URL, HTTP status, and SHA-256 for each byte sequence. Returned passages and citation hashes refer to that run's capture. Replaying evidence uses those saved bytes; a later public page does not change an earlier result.

Money is independently calculated using Decimal: round each ride's minutes upward, apply the included classic allowance per ride, add unlock/residual charges, round money per ride, and charge one membership fee per account/window. All fee expense is allocated to the week containing coverage start. The sample-mix break-even threshold is per account and explicitly approximate for heterogeneous durations. Taxes based on start jurisdiction, parking, penalties and unobserved adjustments are excluded; the accepted inputs contain only classic bikes.

A model answer is accepted only when its exact decision and totals match independently computed costs, its cited justification matches a five-sentence fact template, all three tools and required policy sources were actually observed, and actual calculator operations support both totals. A trusted phase hint narrows the next task using only successful observations and captured policy facts, including the cheaper alternative established by both actual calculator observations; it executes no tool and fabricates no result. The framework still requests every actual call from the model. This is a guided agent demonstration, not an unassisted reasoning benchmark. Failed final answers are retained and never rewritten into accepted answers. Financial facts in the final demonstrations are independently audited against raw rows and captured policy passages as well.

## Bounds, storage, and evidence

Default limits are eight model responses, sixteen proposed/actual tools, 48,000 conservatively charged tokens, 32,768 context and 512 output tokens per response, 120-second request timeout and a 600-second process deadline. A new request must fit its full allowance. Unknown usage is reported as unavailable and charged its reserved allowance. `steps` counts actual framework stream updates, including individual tool-node updates; model requests and actual tool calls are reported separately. The supervisor measures elapsed time and kills the owned process group at its wall deadline. The UI polls for at most twelve minutes and sends one submission.

`POST /api/bikeshare/runs` takes multipart `file` and `pricing_url`, returns 202, and requires a real bearer identity. `GET /api/bikeshare/runs/{id}` returns only the authenticated owner's run. Other users and invalid IDs receive 404. Each upload, policy cache, trace and result lives in that owner's unique private run directory. The worker receives a minimal environment without database/JWT secrets. The server admits at most one pending/active job and executes it in a killable worker. Closing it prevents new jobs and terminates owned children. Authentication runs before multipart parsing; the complete request is byte-limited and time-limited. A transient status-read failure retries the same run, and navigation within the signed-in session preserves its handle. A full page reload clears that in-memory handle; a lost submission response is not automatically resubmitted.

The trace records source commit/dirty state, exact model messages and native call IDs, tool proposals, actual requests/observations, graph updates, usage reservations, and final verification. It contains observations and the model's concise final output; no fabricated reasoning transcript is added. Final acceptance must use committed, clean application source.

Run controlled-response tests separately from live measurements:

```sh
python -m pytest tests/test_hw07_bike*.py -q
ruff check .
ruff format --check .
```

For genuine UI acceptance, load existing credentials into the environment without printing them. Set `HW7_BROWSER_OUTPUT` to a fresh external directory, and `HW7_BIKE_SCENARIO` to `ui`, `frequent`, or `occasional`; run `node scripts/hw07/bike_browser.cjs` with Playwright installed. The `ui` mode checks desktop/tablet/mobile inputs without calling the model. Scenario modes upload the exact committed CSV, click Run once, retain response and real browser captures even on failure, then assert the expected verified decision and clean source. Final evidence is mapped in `reports/hw07/PART4.md`; pilots are separately labeled.
