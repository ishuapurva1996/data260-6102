# DATA 260 assignment submissions

This repository uses SID4 `6102`, port `8702`, prefix `s6102`, seed `6102`, verification seed `266102`, and the Rental Housing Listings domain. One application is extended across assignments, as required by the HW2 instructions.

Repository: [github.com/ishuapurva1996/data260-6102](https://github.com/ishuapurva1996/data260-6102)

## Repository structure

Application code lives in shared root-level `code/` and `src/` folders. Assignment reports and evidence live under `reports/hw01/` and `reports/hw02/`. Run the commands below from the Git repository root unless stated otherwise:

```bash
cd "/Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102"
```

The active web application includes the HW2 Part 1 interface and Part 2 FastAPI backend. The `hw1` Git tag preserves the exact original HW1 source and submission. Historical reports, logs, and recorded results retain their original contents.

```text
data260-6102/
├── code/
│   ├── web_application/
│   │   ├── main.py
│   │   ├── README.md
│   │   └── static/
│   │       ├── index.html
│   │       ├── styles.css
│   │       └── app.js
│   ├── agents_demo.py
│   ├── agents_graph.py
│   ├── hw1_client.py
│   └── Dockerfile
├── src/
│   ├── model_client.py
│   └── agent_graph/
├── reports/
│   ├── hw01/
│   │   ├── raw/
│   │   ├── RUN_LOG.txt
│   │   ├── METRICS.md
│   │   ├── AI_USE.md
│   │   ├── report.pdf
│   │   ├── verification.json
│   │   └── REPRODUCIBLE_RUN_INSTRUCTIONS.md
│   └── hw02/
│       ├── README.md
│       ├── PART3_IMPLEMENTATION.md
│       └── verification_part3.json
├── docs/
│   └── agent_graph.md
├── scripts/
│   └── verify_part3.py
├── AGENT.md
├── DOMAIN_SCHEMA.md
├── requirements.txt
├── requirements-agents.txt
├── package.json
├── tests/
│   ├── test_api.py
│   ├── browser_part2.cjs
│   └── agent_graph/
└── README.md
```

Course instructions, lecturer practice scripts, implementation plans, and agent working notes remain outside this repository in the sibling `HW1 assignment instructions/` and `HW2/agent_outputs/` folders. HW2 extends the shared application; there are no separate HW1/HW2 application copies.

## Current HW2 progress

The shared application provides create, per-listing editing, highest-ID deletion, per-row deletion, and title/address search through FastAPI. It retains the 375px layout and visible loading, empty, and error states. Use a separate web environment so its dependencies stay independent of the Part 3 agent environment:

```bash
python3.12 -m venv .venv-web
source .venv-web/bin/activate
python -m pip install -r requirements.txt
python code/web_application/main.py
```

Open [the application](http://127.0.0.1:8702/) or [the API documentation](http://127.0.0.1:8702/docs). Records survive page reloads; restarting the single server process restores seed IDs 1 and 2. Stop it with `Control-C`. Only one application can use port 8702 at a time.

See the [web application guide](code/web_application/README.md) for Docker, API tests, browser checks, and controlled screenshot aids. The Part 1 and Part 2 screenshot guides remain outside Git at `../HW2/agent_outputs/SCREENSHOT_EVIDENCE_PLAN.md` and `../HW2/agent_outputs/PART2_SCREENSHOT_EVIDENCE_PLAN.md`. [The complete HW2 report and submission package](reports/hw02/README.md) include all four parts, raw results, screenshots and reproduction instructions.

### HW2 Part 3 - Planner/Reviewer graph

Part 3 uses LangGraph to draft listing metadata, review it, and request revisions within a configurable worker-turn limit. It reuses the shared model adapter and runs directly from the CLI. With Ollama running and `qwen3:1.7b` installed, set up the separate agent environment:

```bash
python3.12 -m venv .venv-agents
source .venv-agents/bin/activate
python -m pip install -r requirements-agents.txt
python code/agents_graph.py --input-json reports/hw02/cases/part3_listing.json --evidence-dir reports/hw02/raw/part3
```

If `.venv-agents` is already prepared, run `.venv-agents/bin/python code/agents_graph.py --input-json reports/hw02/cases/part3_listing.json`.

See the [Part 3 usage and architecture guide](docs/agent_graph.md) for turn counting, response validation, controlled Reviewer mode, and test commands. The [implementation results](reports/hw02/PART3_IMPLEMENTATION.md) link the recorded tests, real-model runs, and screenshots. The [combined HW2 report](reports/hw02/report.pdf) includes Parts 1-4. The `hw2-code` tag identifies verified runtime source; `hw2` preserves the original submission package, and `hw2-report-v2` identifies the revised report with closing GitHub links. Follow the [submission checklist](reports/hw02/SUBMISSION_CHECKLIST.md) before submitting online.

## Reproducing the original HW1 submission

The tag `hw1` resolves to commit `6f7d27d4063c4483386803bfdd80d2e617c907be`. To inspect it without changing this checkout, use `git show refs/tags/hw1:README.md`. To reproduce it separately, create a detached worktree outside this submission repository:

```bash
git worktree add --detach ../data260-6102-hw1-reproduction refs/tags/hw1
```

Follow that worktree's README for exact original behavior. The commands below describe the shared checkout and its retained HW1 agent workflows. The current web app has since been improved for HW2.

## Homework 1 files

- `reports/hw01/report.pdf` - complete report and screenshots
- `DOMAIN_SCHEMA.md` - Part 1 entity fields and category values
- `reports/hw01/RUN_LOG.txt` - recorded commands, timestamps, and results
- `reports/hw01/raw/` - Part 2 output, all 40 Part 3 runs, and Part 4 token counts
- `reports/hw01/METRICS.md` - Part 3 tables and interpretation
- `reports/hw01/AI_USE.md` - required AI-assistant disclosure
- `AGENT.md` - strict bullet-only code-review instructions for Part 4
- `reports/hw01/verification.json` - generated self-check result
- `reports/hw01/REPRODUCIBLE_RUN_INSTRUCTIONS.md` - commands for reproducing all four parts

## Environment

Use Python 3.11 or 3.12. The recorded local model was `qwen3:1.7b` because the requested `qwen3:8b` download did not complete reliably on the local machine.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r reports/hw01/requirements-part2.txt
ollama serve
ollama pull qwen3:1.7b
```

## Part 1 - Web application

```bash
docker build -f code/Dockerfile -t rental-housing-app:latest .
docker run --rm --name rental-housing-web -p 127.0.0.1:8702:8702 rental-housing-app:latest
```

Open `http://localhost:8702`. This container serves the current interface and FastAPI backend. For the exact HW1 interface and its historical Docker commands, build at the `hw1` tag. The HW1 report contains the historical one-task AWS ECS deployment and public-IP screenshots.

## Part 2 - Planner, Reviewer, and Finalizer

Run from the Git repository root:

```bash
python code/agents_demo.py --title "Modern Two-Bedroom Apartment Near Downtown San Jose" --content "Bright two-bedroom apartment with in-unit laundry, covered parking, pet-friendly policies, and convenient light rail access near downtown San Jose." --model qwen3:1.7b --temperature 0.0
```

The Planner response is passed to the Reviewer in its raw form. The deterministic Python Finalizer then parses, normalizes, validates, and publishes exactly three input-derived tags plus a summary of at most 25 words. The exact recorded output and explanation are in `reports/hw01/report.pdf` and `reports/hw01/RUN_LOG.txt`.

## Part 3 - Non-determinism experiment

The fixed input is `reports/hw01/cases/nondeterminism_input.json`. The recorded experiment produced 20 successful runs at each temperature:

```bash
python reports/hw01/run_nondeterminism.py --model qwen3:1.7b --count 20 --temperatures 0.7 0.0 --timeout 120 --max-errors 10
```

The checked-in output already exists, so use `--resume` to validate it without model calls or `--overwrite` only when deliberately replacing the experiment. Results are explained in [`reports/hw01/METRICS.md`](reports/hw01/METRICS.md).

## Part 4 - Model client and token accounting

All Ollama calls go through `src/model_client.py`. The recorded five-turn demo used:

```bash
python code/hw1_client.py --demo --model qwen3:1.7b --temperature 0.0 --timeout 120 --output reports/hw01/raw/part4_five_turn_conversation.txt --metrics-output reports/hw01/raw/part4_token_counts.json
```

`/stats` reports the turn count, cumulative input/output tokens, and serialized conversation-history length without adding anything to the history.

### Required concepts

Prior context is resent because each model request is stateless; the earlier messages must be included again if the next response needs them. A system prompt defines the model's role and conversation-wide rules, while a user message supplies the current task. Input tokens grow because every turn resends an increasingly long history. Growth is eventually limited by the model's finite context window, so older content must be trimmed or summarized.

## Verification

From the Git repository root:

```bash
make -C reports/hw01 verify-hw01 PYTHON=python NODE_BIN=node
```

The verifier checks the current shared checkout. Its default output replaces `reports/hw01/verification.json`; use `python reports/hw01/verify_hw01.py --output /tmp/data260-verification.json` to preserve the recorded submission result. The submitted PDF remains at `reports/hw01/report.pdf` and is unchanged from the `hw1` tag.

## HW2 Part 4 — schema validation and loop safety

The shared Planner–Reviewer graph now validates Planner output with Pydantic and retries within the worker-turn ceiling. The completed 75-run experiment uses real `qwen3:1.7b` calls with frozen inputs and settings.

- [Measured tables and ceiling recommendation](reports/hw02/METRICS.md)
- [Reproduction and offline verification](reports/hw02/REPRODUCIBLE_RUN_INSTRUCTIONS.md)
- [Scoped Part 4 verification](reports/hw02/verification_part4.json)
- [Part 4 evidence and screenshots](reports/hw02/PART4_IMPLEMENTATION.md)

The [complete HW2 report](reports/hw02/report.pdf), AI-use answers, raw evidence and passing tagged verification are included. The published HW2 branch is [codex/fix-hw1-form](https://github.com/ishuapurva1996/data260-6102/tree/codex/fix-hw1-form). Collaborator confirmation and the course-portal upload remain pending.
