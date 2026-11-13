# HW10 evaluator

## Single trace for the benchmark

Run from the repository root immediately after exporting the linked case.

```bash
python -m scripts.hw10.evaluate pipeline \
  --evidence-root "$HW10_EVIDENCE_ROOT" --trace-id "$TRACE_ID"
```

Replace `--trace-id` with `--case-id` to select by dataset case ID. The input is
`tracing/linked_cases.jsonl` relative to the evidence root. With no
`--output-dir`, the evaluator writes to `EVIDENCE_ROOT/evaluation/`.
Pass `--output-dir` to put evaluation output in a different directory.

- `pipeline_scores.jsonl` contains one record per successful evaluation with
  `trace_id`, `correlation_id`, `case_id`, `evaluation_id`, `question`,
  `reference_facts`, `plan`, `draft`, `final_answer`, and `messages`. The
  `final` alias supplies the same answer text to the dashboard. Each entry
  under `scores.planner`, `scores.writer`, and `scores.reviewer` has a
  `score` (1–5), `normalized_score` (0–1), and `reason`. The
  `final_minus_draft` and `interpretation` fields compare the two answers.
- `spans.jsonl` contains the completed `evaluation` span with the same
  `trace_id` and `evaluation_id`, UTC start and end, monotonic
  `duration_ms`, `status` (`ok` or `error`), and nullable `error`.
  Use this span's end time to measure ingress-to-evaluation latency.
- Failures with no resolvable trace ID are recorded separately in
  `pipeline_failures.jsonl`, together with other evaluation failures.
  The command exits 0 on success and 1 on an evaluation failure. Use the
  `evaluation_id` in the command's JSON output to match the score and
  span from this invocation, including when a trace is evaluated again.

The local judge defaults to `qwen2.5:7b` on `http://127.0.0.1:11434`.
Use `--model-digest` to require the digest recorded in the live handoff.
The initial budgets are 5 seconds to find the linked case, 45 seconds
for Ollama connection/read timeouts, and 180 seconds of wall time for the
entire case. A failed judge request or invalid judge response gets at most
one retry per metric within the case deadline. Run evaluations serially.

The evaluator checks the original Inbox, Planner, Writer, and Reviewer
records from the exporter. It verifies the shared correlation ID and the
Kafka topic, partition, and offset consumed by each downstream stage.
It checks the saved question, facts, and carried text against the payloads
before using the exact plan, draft, and approved final answer.

## Local judge setup

Use a separate Python 3.12 environment for `requirements-hw10-evaluation.txt`.

```bash
python3.12 -m venv "$HW10_EVAL_RUNTIME/venv"
"$HW10_EVAL_RUNTIME/venv/bin/python" -m pip install -r requirements-hw10-evaluation.txt
```

Run inference after the A2 freeze and during the assigned live window. Use the
loopback Ollama server with the judge model installed. The command checks the
local model digest and records it with the DeepEval version and settings. The
default judge uses the same model tag as the HW9 pipeline. Record the actual
pipeline model and digest alongside the judge settings when collecting results.

DeepEval 3.9.4 uses fixed evaluation steps and score bands for plan quality and
helpfulness. The Ollama adapter uses JSON mode, temperature 0, seed 6102, an
8,192-token context, and a 256-token output limit. Each measurement calls the
judge afresh. Each draft and final uses the same helpfulness steps, question,
and reference facts. The judge sees neither the human labels nor the stage
name in the helpfulness prompt.

The rubric gives a 1 to a very poor or materially wrong answer, a 2 to an
answer with major omissions, a 3 to a partly helpful answer, a 4 to a mostly
correct and useful answer, and a 5 to an accurate, relevant, and complete
answer. For G-Eval's normalized score `s`, compute `1 + 4 * s` and round to
the nearest integer with halves rounded up. The evidence retains both scores.

## Frozen validation

```bash
python -m scripts.hw10.evaluate validate --evidence-root reports/hw10/raw \
  --tracing-sha "$A1_SHA" --freeze-sha "$A2_SHA" \
  --cases-sha256 "$CASES_SHA256" --labels-sha256 "$LABELS_SHA256" \
  --model-digest "$JUDGE_DIGEST"
```

The runner requires A1 to precede A2 and A2 to be in the current history.
It verifies both frozen blobs against the receipt and the working files. It
requires 20 unique draft cases and one integer label per case. The judge
receives each original draft, its question, and its facts in three fresh
passes under the same settings.

`evaluation/judge_scores.csv` holds the 60 raw scores and reasons with case,
trace, pass, and run IDs. `evaluation/judge_validation.json` holds the freeze
SHA, model and rubric metadata, pass status, and comparisons by case ID. It
uses pass 1 for tie-aware Spearman and mean absolute difference. If either
score set is constant, Spearman is `null`. For each draft, repeatability uses
the difference between its highest and lowest score across the three passes.
The changed rate is a fraction from 0 to 1.

An incomplete study exits 1 and leaves its errors in
`evaluation/judge_failures.jsonl`. Rerun with the same settings to obtain a
complete study. Check that the study ID matches between the CSV and JSON
before using the metrics.

## Offline checks

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_hw10_evaluation.py
```

The tests create their own synthetic records and use a simulated judge.
