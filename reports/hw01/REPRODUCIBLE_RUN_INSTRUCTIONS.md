# Homework 1 Reproducible Run Instructions

Run every command from the Git repository root unless a command says otherwise:

```bash
cd "/Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102"
```

All paths below are relative to the repository root. The shared web app now includes HW2 Parts 1 and 2, with a FastAPI backend; the remaining HW1 agent workflows are retained. The submitted report and recorded logs retain their original contents. For exact HW1 source and behavior, create a separate historical checkout with `git worktree add --detach ../data260-6102-hw1-reproduction refs/tags/hw1`, then follow its README. This does not add a duplicate application to the submission repository.

## Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r reports/hw01/requirements-part2.txt
ollama serve
ollama pull qwen3:1.7b
```

## Part 1 - Web application

```bash
docker build --platform linux/amd64 -f code/Dockerfile -t rental-housing-app:latest .
docker run -d --name rental-housing-hw1 -p 127.0.0.1:8702:8702 rental-housing-app:latest
```

This serves the current shared interface and API. Stop any Python server using port 8702 before starting the container. Open `http://localhost:8702` and stop the container afterward with:

```bash
docker stop rental-housing-hw1
docker rm rental-housing-hw1
```

## Part 2 - Agent pipeline

```bash
python code/agents_demo.py --title "Modern Two-Bedroom Apartment Near Downtown San Jose" --content "Bright two-bedroom apartment with in-unit laundry, covered parking, pet-friendly policies, and convenient light rail access near downtown San Jose." --model qwen3:1.7b --temperature 0.0
```

## Part 3 - Non-determinism experiment

The checked-in raw result already contains 20 successful runs at both temperatures. Validate it without new model calls using:

```bash
python reports/hw01/run_nondeterminism.py --model qwen3:1.7b --count 20 --temperatures 0.7 0.0 --timeout 120 --max-errors 10 --resume
```

Remove `--resume` and add `--overwrite` only when deliberately replacing the recorded 40-run experiment.

## Part 4 - Model client and token accounting

```bash
python code/hw1_client.py --demo --model qwen3:1.7b --temperature 0.0 --timeout 120 --output reports/hw01/raw/part4_five_turn_conversation.txt --metrics-output reports/hw01/raw/part4_token_counts.json --overwrite
```

## Complete verification

```bash
make -C reports/hw01 verify-hw01 PYTHON=python NODE_BIN=node
```

The command must finish with `"status": "pass"` and updates `reports/hw01/verification.json`. To check the current checkout while preserving the recorded HW1 result, run `python reports/hw01/verify_hw01.py --output /tmp/data260-verification.json` instead.
