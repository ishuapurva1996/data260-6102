# data260-6102

DATA 260 coursework repository. Homework 1 uses SID4 `6102`, port `8702`, prefix `s6102`, seed `6102`, verification seed `266102`, and the Rental Housing Listings domain.

Repository: [github.com/ishuapurva1996/data260-6102](https://github.com/ishuapurva1996/data260-6102)

## Repository structure

Application code is kept in shared root-level folders so it can be extended in later homework assignments. Homework-specific evidence stays under `reports/hw01/`.

```text
data260-6102/
├── code/
│   ├── web_application/
│   │   ├── index_hw1.html
│   │   ├── css_style.css
│   │   └── script_hw.js
│   ├── agents_demo.py
│   ├── hw1_client.py
│   └── Dockerfile
├── src/
│   └── model_client.py
├── reports/
│   └── hw01/
│       ├── raw/
│       ├── RUN_LOG.txt
│       ├── METRICS.md
│       ├── AI_USE.md
│       ├── report.pdf
│       ├── verification.json
│       └── REPRODUCIBLE_RUN_INSTRUCTIONS.md
├── AGENT.md
├── DOMAIN_SCHEMA.md
└── README.md
```

## Homework 1 files

- `reports/hw01/report.pdf` - complete report and screenshots
- `DOMAIN_SCHEMA.md` - Part 1 entity fields and category values
- `reports/hw01/RUN_LOG.txt` - recorded commands, timestamps, and results
- `reports/hw01/raw/` - Part 2 output, all 40 Part 3 runs, and Part 4 token counts
- `reports/hw01/METRICS.md` - Part 3 tables and interpretation
- `reports/hw01/AI_USE.md` - required AI-assistant disclosure
- `reports/hw01/PART2.md` - Part 2 command, answers, screenshots, and explanation
- `reports/hw01/PART4.md` - Part 4 implementation, token results, and explanations
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
docker build --platform linux/amd64 -t rental-housing-app:latest code
docker run -d --name rental-housing-hw1 -p 8702:80 rental-housing-app:latest
```

Open `http://localhost:8702`. The report also contains the recorded one-task AWS ECS deployment and public-IP screenshots.

## Part 2 - Planner, Reviewer, and Finalizer

Run from the repository root:

```bash
python code/agents_demo.py --title "Modern Two-Bedroom Apartment Near Downtown San Jose" --content "Bright two-bedroom apartment with in-unit laundry, covered parking, pet-friendly policies, and convenient light rail access near downtown San Jose." --model qwen3:1.7b --temperature 0.0
```

The Planner response is passed to the Reviewer in its raw form. The deterministic Python Finalizer then parses, normalizes, validates, and publishes exactly three input-derived tags plus a summary of at most 25 words. More detail is in [`reports/hw01/PART2.md`](reports/hw01/PART2.md).

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

From the repository root:

```bash
make -C reports/hw01 verify-hw01 PYTHON=python NODE_BIN=node
```

Before submission, create the final commit and tag it `hw1`. Push the branch and tag only after confirming that the submitted PDF is byte-for-byte identical to `reports/hw01/report.pdf` at that tagged commit.
