# Reproduce the retrieval comparison

Run these commands from the repository root. The experiment needs no web server, API key or generated answer. The recorded environment is Python 3.12.14 on macOS arm64. Keep retrieval dependencies separate from the web environment.

The report uses run `manual-screenshots-20260921`, recorded on September 21, 2026, Pacific time (September 22 UTC). The original `baseline-20260920` experiment is retained unchanged. Complete hits and vector sidecars were identical in the two runs; search timings and timestamps changed.

## Install and prepare the local model

```bash
python3.12 -m venv .venv-retrieval
.venv-retrieval/bin/python -m pip install -r requirements-retrieval.txt
.venv-retrieval/bin/python code/retrieval_compare.py download-model
```

The download command caches the public model revision pinned in `experiment_config.yaml` under ignored `.venv-retrieval/model-cache`. Set `HW3_MODEL_CACHE` to use another writable cache. Subsequent runs enforce local-files-only model loading and CPU execution with one PyTorch thread. OpenAI packages are transitive dependencies of `llama-index`; the experiment uses no OpenAI client or API, and answer generation is disabled.

The recorded Python runtime was 3.12.14 at `/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`. A conventional local Python 3.12 installation is sufficient. Use the pinned packages where compatible; hardware, Python and package changes can affect timings or numerical rounding.

## Check the saved results

```bash
.venv-retrieval/bin/python -m pytest tests/retrieval -q
.venv-retrieval/bin/python code/retrieval_compare.py check-inputs
.venv-retrieval/bin/python code/retrieval_summarize.py \
  --run-dir reports/hw03/raw/part2/manual-screenshots-20260921 --check
.venv-retrieval/bin/python scripts/verify_hw03_part2.py \
  --run-dir reports/hw03/raw/part2/manual-screenshots-20260921 \
  --require-report --output /tmp/hw3-part2-verification.json
```

The summarizer uses only Python's standard library and can run with `python3`. It joins saved answer-support annotations with raw hits and timing samples. Omit `--check` to regenerate `summary.json` and the shared `reports/hw03/METRICS.md`. Use `--output` to choose a different Markdown destination. The verifier needs NumPy and PyYAML, but its default mode needs neither model files nor network. Add `--smoke` to check a real cached-model embedding. The temporary output path above avoids overwriting an older verification receipt.

To check the original baseline separately, read its metrics from the commit that preceded this refresh:

```bash
git show 85a6dd8f2dfe2a89a8301a3accc8aef4d533c443:reports/hw03/METRICS.md > /tmp/hw3-baseline-metrics.md
python3 code/retrieval_summarize.py \
  --run-dir reports/hw03/raw/part2/baseline-20260920 \
  --output /tmp/hw3-baseline-metrics.md --check
```

## Run a new experiment

The retained Tiny Shakespeare file in `raw/part2/warmup/tinyshakespeare.txt` supports a separate warm-up using its first 12,000 characters. It is excluded from the housing corpus and comparison metrics.

```bash
.venv-retrieval/bin/python code/retrieval_compare.py warmup --run-id shakespeare-reproduction
.venv-retrieval/bin/python code/retrieval_compare.py run \
  --freeze-commit 08bd6e0495ce03281aa8fab7f70ac0b51e1c1442 \
  --run-id retrieval-reproduction
```

Choose unused run IDs: existing directories cannot be overwritten. The runner rejects modified/uncommitted inputs, changed/uncommitted experiment code and a freeze commit outside the current ancestry. The frozen questions, source snapshots and settings must match the input commit byte for byte. Preserve that ancestry when integrating changes.

The comparison uses `k=3`, one unmeasured search warm-up per question/method and ten measured searches. Query embedding, index building, document re-embedding, logging and token audits occur outside the search timer. Each method creates a separate in-memory `SimpleVectorStore` index. Query vectors and the three recomputed document vectors are saved in JSON sidecars. Original store ranks remain available when tied scores are ordered by node ID.

Before summarizing a new run, review each complete returned central passage and available context against the frozen expected answer and record `annotations.json`. Do not infer answer support from scores or source identity. For the current run, Codex reviewed all 45 hits and checked their full texts and vectors against the original baseline; the new annotations record that review. The user screenshots document the resulting outputs. The existing five questions already produced rank-1 failures above the predeclared 0.50 threshold, so no extra diagnostic queries were needed.

## Capture the actual Terminal output

The user took the five current Part 2 screenshots in Terminal. They show saved output from the fresh experiment, without a browser evidence viewer. To display the same three Q1 results:

```bash
sed -n '/^token | Q1 |/,/^Search-only/p' \
  reports/hw03/raw/part2/manual-screenshots-20260921/console.txt
sed -n '/^semantic | Q1 |/,/^Search-only/p' \
  reports/hw03/raw/part2/manual-screenshots-20260921/console.txt
sed -n '/^sentence_window | Q1 |/,/^Search-only/p' \
  reports/hw03/raw/part2/manual-screenshots-20260921/console.txt
```

Capture each block with all three result rows and search durations visible. The supplied files are `11-token-output.png`, `12-semantic-output.png` and `13-sentence-window-output.png` under `reports/hw03/screenshots/manual/`.

Display the comparison table and complete high-similarity failure:

```bash
sed -n '13,19p' reports/hw03/raw/part2/manual-screenshots-20260921/METRICS.md
.venv-retrieval/bin/python reports/hw03/raw/manual-captures/show_retrieval_failure.py
```

The corresponding files are `14-comparison-table.png` and `15-high-score-failure.png`. The failure helper reads Q2's actual rank-1 token result, checks it against the saved question and prints the complete returned chunk. The [capture manifest](../raw/manual-captures/capture-manifest.json) identifies the original supplied files and hashes.

The older `screenshots/part2/` images are browser views of the original baseline, documented in `SCREENSHOT_CAPTURE.md`. They remain historical evidence and are not the current report figures.

## Corpus extraction

The optional `python3 reports/hw03/corpus/extract_corpus.py` step extracts text from the retained original PDFs using Poppler. Retrieval runs use the already-frozen text, so extraction is unnecessary. Other Poppler versions may change whitespace and break the frozen hashes. Gold-page images and the source audit document the original extraction.
