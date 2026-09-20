# Part 2 reproducible run instructions

Run commands at the root of the Part 2 worktree or a later integrated repository. These commands need no Part 1 server, API key, paid service or generated answer. The recorded environment is Python 3.12.14 on macOS arm64. Use a separate environment; do not install into the web application's environment.

## Install and prepare the local model

```bash
uv venv --python 3.12 .venv-retrieval
uv pip install --python .venv-retrieval/bin/python -r requirements-retrieval.txt
.venv-retrieval/bin/python code/retrieval_compare.py download-model
```

`download-model` is the only model-network step. It downloads the pinned public model revision in `experiment_config.yaml` to the ignored `.venv-retrieval/model-cache`. An alternative writable cache can be set with `HW3_MODEL_CACHE`. Subsequent runs enforce local-files-only loading and CPU execution with one PyTorch thread. OpenAI packages are transitive dependencies of the assignment's `llama-index` metapackage; no OpenAI client or API is used by this experiment, and the LLM is disabled.

For the original sandboxed environment, `UV_CACHE_DIR=/tmp/hw3-part2-uv` was used for installation and Python 3.12.14 was the bundled runtime at `/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`. A conventional local Python 3.12 installation is sufficient on another host; install the exact pinned packages where compatible. Hardware, Python build and package changes can alter timings or numerical roundoff.

## Verify saved evidence without retrieving again

```bash
.venv-retrieval/bin/python -m pytest tests/retrieval -q
.venv-retrieval/bin/python code/retrieval_compare.py check-inputs
.venv-retrieval/bin/python code/retrieval_summarize.py \
  --run-dir reports/hw03/raw/part2/baseline-20260920 --check
.venv-retrieval/bin/python scripts/verify_hw03_part2.py \
  --run-dir reports/hw03/raw/part2/baseline-20260920 \
  --require-report --output reports/hw03/part2/verification.json
```

The summarizer is standard-library-only: it can also be run with `python3` and does not import an embedding model or LlamaIndex. It joins the saved manual annotations with raw hits and search samples. Omit `--check` to regenerate `summary.json` and `reports/hw03/METRICS.md`. The verifier uses NumPy and PyYAML, but its default mode needs neither model files nor network. Add `--smoke` to explicitly test a real cached model embedding.

## Reproduce the warm-up and baseline

The full Tiny Shakespeare download is retained in `raw/part2/warmup/tinyshakespeare.txt`; only its first 12,000 characters are used for a separate warm-up. It is never added to the graded corpus or baseline metrics. Its source URL and SHA-256 are recorded in each warm-up run.

```bash
.venv-retrieval/bin/python code/retrieval_compare.py warmup --run-id shakespeare-reproduction
.venv-retrieval/bin/python code/retrieval_compare.py run \
  --freeze-commit 08bd6e0495ce03281aa8fab7f70ac0b51e1c1442 \
  --run-id baseline-reproduction
```

Use a new run ID; existing run directories are never overwritten. The runner rejects modified/uncommitted inputs, a freeze commit that is not an ancestor, or changed/uncommitted experiment code. The frozen questions, source snapshots and settings must match the input commit byte for byte. Preserve the freeze commit when integrating; do not squash or cherry-pick away its ancestry. A merge that preserves Part 2 history is appropriate for the later integration owner.

The baseline has k=3, one unmeasured search warm-up per question/method, and 10 measured searches. Query embedding, index building, returned-text re-embedding, logging and token audits occur outside the search timer. Each method uses a new in-memory SimpleVectorStore index. Its query vector and the three explicitly recomputed document vectors are saved in separate JSON sidecars. Original store ranks remain available even when tied scores are ordered deterministically by node ID.

New runs require fresh explicit answer-support review before summarization: read the complete returned central text and available context against frozen expected answers and record `annotations.json`. Do not copy labels by score or source identity. The saved annotations show the format and rationale. The baseline already includes multiple rank-1 failures at the predeclared 0.50 threshold, so no extra diagnostic questions were needed. Diagnostic querying is supported by `run --diagnostic --questions reports/hw03/diagnostic_questions.yaml --freeze-commit <new-input-commit> --run-id <new-id>`; keep diagnostic metrics in a separate output file. The current final verifier is deliberately scoped to the complete baseline campaign, whose required failure is present.

## Screenshots and corpus extraction

`part2/build_evidence_view.py` renders saved console excerpts and raw metrics to HTML. Actual browser screenshots of these pages are in `screenshots/part2/`; they are explicitly labelled as views of saved run output. `part2/SCREENSHOT_CAPTURE.md` records capture provenance. No screenshot values were typed or drawn onto images.

The optional `python3 reports/hw03/corpus/extract_corpus.py` step re-extracts the retained original PDFs using Poppler. It is not needed to rerun retrieval over the frozen text. Re-extraction with different Poppler versions may change whitespace and therefore fail the frozen hashes; retain the committed snapshots for this baseline. Gold-page images and the source audit document the original extraction.
