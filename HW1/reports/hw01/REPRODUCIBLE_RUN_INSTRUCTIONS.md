# Homework 1 Reproducible Run Instructions

Run every command from the `HW1/` assignment root unless a command says otherwise. From the Git repository root, first run:

```bash
cd HW1
```

All paths below are relative to that assignment root. The historical Git tag `hw1` preserves the original submission and its earlier repository layout. The submitted report and recorded logs retain their original contents and historical paths.

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
docker build --platform linux/amd64 -t rental-housing-app:latest code
docker run -d --name rental-housing-hw1 -p 8702:80 rental-housing-app:latest
```

Open `http://localhost:8702` and stop the container afterward with:

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

The command must finish with `"status": "pass"` and update `reports/hw01/verification.json`.
