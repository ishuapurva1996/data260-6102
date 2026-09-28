# HW4 Part 4 local handoff

Part 4 implementation, 22 final experiment calls, evaluation, and report material are available locally. **The required complete, supported, cited C answer remains incomplete.** C did demonstrate both exact required refusals. Failed answers and earlier attempts are preserved; no model answer was replaced. This is not a whole-homework submission or a successful completion claim for the remaining demonstration.

## Checkout and selected evidence

- Worktree: `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend`
- Branch: `codex/hw4-part2-backend`; unchanged base HEAD `421c77ddca9ce998e5088dd305ea4da9bb714238`.
- Selected run: `reports/hw04/raw/part4/scored-20260928-03/`, started `2026-09-28T04:38:38.528073+00:00`, finished `2026-09-28T04:41:35.148210+00:00`.
- Exact code/input hashes and dirty state: selected `run_metadata.json`; frozen code, configuration, sources and question keys: `frozen/`; generation-file hashes: `evidence_hashes.json`.
- `responses.jsonl` preserves all 22 exact outputs and raw Ollama responses. `requests.jsonl` preserves requests before the call. `retrievals.jsonl`, `retrieved_chunks.txt` and `RUN_LOG.txt` retain every candidate, score, text, source, timestamp and submitted prompt. `sweep_references.json` explicitly reuses main k=3 rows.
- `judgments.json` identifies the assistant evaluator and contains exact support quotes and reasons. `evaluation.csv`, `comparison.csv`, `k_sweep.csv`, `evaluation_summary.csv` and `summary.json` are derived tables.
- Report: [REPORT_SECTION.md](REPORT_SECTION.md). Verification: [verification.json](verification.json). Screenshots: [manifest](../screenshots/part4/scored-20260928-03/manifest.json); method: [SCREENSHOT_METHOD.md](SCREENSHOT_METHOD.md).
- Source preparation/coverage proof: [CORPUS_MANIFEST.json](CORPUS_MANIFEST.json), [source_audit.json](source_audit.json), [preflight_review.json](preflight_review.json), selected `gold_chunk_audit.json`.
- Development settings: [calibration.json](calibration.json). Failed attempts and reasons: [REMEDIATION.md](REMEDIATION.md). All earlier raw directories remain separate.

## Environment and cache

Dedicated environment: `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend/.venv-rag`; Python 3.12.13. Hardware: Apple M4, 24 GiB RAM, macOS 15.7.4. The setup directory records the actual packages, hardware, service flags and model files. Existing application environments were not changed.

- Dependencies: `requirements-rag.txt`; exact installed lock: `reports/hw04/raw/part4/setup/requirements-rag.lock.txt`.
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; absolute cache `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend/.cache/hw04-rag/embeddings`.
- Generator: Ollama 0.33.0, `qwen2.5:3b`, Q4_K_M, digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`; model store `/Users/pragyaapurva/.ollama/models`.
- Exact-text generation tokenizer: `Qwen/Qwen2.5-3B-Instruct`, revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`; absolute cache `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend/.cache/hw04-rag/generator-tokenizer`.
- All inference uses local assets. Hugging Face is offline during experiments; Ollama runs on `127.0.0.1:11434` with cloud disabled. Public asset downloads were explicit setup operations. Model manifest, tokenizer and weight hashes are in `setup/model_assets_qwen25.json`.
- Fixed final options: seed 6102, temperature 0, context window 4096, maximum output 768, `think:false`, top-k 3 in the main matrix, cutoff 0.50, maximum C evidence 1800 generator tokens, 128 template tokens reserved. A/B/C have independent requests with no prior conversation.

## Exact reproduction commands

Use the existing environment/cache for offline reproduction. Each run/capture command requires a **new** output directory and refuses to replace existing evidence. A fresh run can differ across runtime/hardware versions despite a fixed seed; preserve its own outputs and judge those outputs separately.

```sh
cd '/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend'
.venv-rag/bin/python -m pytest -q tests/test_hw04_rag.py tests/test_hw04_rag_evaluation.py
.venv-rag/bin/python -m py_compile code/rag.py src/rag/pipeline.py src/rag/runner.py src/rag/evaluation.py scripts/verify_hw04_part4.py
```

If rebuilding a missing environment, install into a new dedicated environment; do not replace the application environment. After these commands, use `.venv-rag-reproduction/bin/python` in place of `.venv-rag/bin/python` in the remaining commands:

```sh
uv venv --python 3.12 .venv-rag-reproduction
uv pip install --python .venv-rag-reproduction/bin/python -r reports/hw04/raw/part4/setup/requirements-rag.lock.txt
```

Explicit public downloads are needed only if the pinned assets are missing. The source documents are already retained, so no live refetch is needed:

```sh
.venv-rag/bin/python code/rag.py download-model
.venv-rag/bin/python code/rag.py download-tokenizer
```

Start an owned local service in a separate terminal only if port 11434 is free. Do not terminate or replace an unrelated listener:

```sh
OLLAMA_NO_CLOUD=1 OLLAMA_NOPRUNE=1 ollama serve
```

If the selected generator is missing, run `ollama pull qwen2.5:3b`; the runner requires the recorded digest and fails if that public tag now points elsewhere. Preserve the original pinned model rather than silently accepting a new digest. With the owned service running:

```sh
.venv-rag/bin/python code/rag.py inspect --output reports/hw04/raw/part4/reproduction-development-01
.venv-rag/bin/python code/rag.py pilot --output reports/hw04/raw/part4/reproduction-pilot-01
.venv-rag/bin/python code/rag.py run --config reports/hw04/raw/part4/scored-20260928-03/frozen/experiment_config.json --output reports/hw04/raw/part4/reproduction-scored-01
```

The `inspect` command builds/audits the actual index and development retrievals. `pilot` makes eight development C calls. `run` makes exactly 18 main and four extra sweep calls. It prints retrieved chunks before generation and writes its own log; additional shell redirection is optional. Reusing the selected configuration requires its referenced source, calibration and model assets to retain the selected hashes. Frozen source/code copies are the authoritative record if later development changes live files.

Evaluation of a **new** run requires reading its actual outputs and supplied evidence and authoring a new `judgments.json` using the schema in `src/rag/evaluation.py`. Do not copy old scores onto new outputs. To recompute the existing selected tables without any model call:

```sh
.venv-rag/bin/python - <<'PY'
from src.rag.evaluation import write_evaluation
write_evaluation('reports/hw04/raw/part4/scored-20260928-03')
PY
```

Capture real browser views of the saved selected outputs to a new directory:

```sh
'/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node' scripts/capture_hw04_part4.cjs --run reports/hw04/raw/part4/scored-20260928-03 --output reports/hw04/screenshots/part4/reproduction-capture-01
```

The bundled Playwright package is `/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`. PNGs are genuine Chromium captures of saved local results, clearly labeled as such; they are not live terminal captures. Each response view places the actual frozen code excerpt immediately above its unedited output. The k=3 sweep views reuse the corresponding main captures.

Offline verification, writing a fresh receipt:

```sh
.venv-rag/bin/python scripts/verify_hw04_part4.py --run reports/hw04/raw/part4/scored-20260928-03 --report reports/hw04/part4/REPORT_SECTION.md --output reports/hw04/part4/verification-reproduction.json
```

An exit code of 1 is currently expected because the required C supported-answer demonstration failed. This does not indicate missing calls or permission to replace answers. The verifier proves artifact consistency and exact quote presence; semantic truth remains an identified assistant judgment requiring student review.

## Remaining work and scope boundary

The smallest unresolved Part 4 step is a general development-tested improvement that produces at least one complete, supported, cited C answer while retaining both exact refusals, followed by a new full frozen 22-call comparison and fresh evaluation/captures. Q3 is the clearest diagnostic: all required facts reached C, but the selected model emitted only `[1]`. Q1 and Q2 also expose retrieval misses. No test-specific answers, hidden extra retrieval, selective output replacement, or relaxed scoring should be used. Reasonable development and three full scored attempts are retained; the current receipt honestly marks the demonstration incomplete.

Student review of code, semantic judgments and explanation remains. Later whole-homework work must integrate Parts 1–4 into the required PDF, confirm the repository/collaborator details, retain the required identity constants and AI-use disclosure, and perform separately authorized final tagged verification. This task did not assemble that PDF, change database state, rerun the old benchmark, commit, push, create a PR, merge, deploy or create/change a tag. Parts 1–3's saved 46/46 receipt remains its historical verification, not a new test claim.

## Delivery verification results

- Focused pipeline/evaluation/verifier suite: **28 passed in 0.08 seconds**, [saved output](../raw/part4/setup/tests-delivery-28.txt); compilation passed. Synthetic unit fixtures are not real experiment evidence.
- Selected run: **22/22 complete calls**, 18 main answers and four distinct sweep answers; six sweep references reuse two main k=3 results.
- Main accuracy: **A 2/6, B 3/6, C 2/6**; answerable accuracy A 0/3, B 2/3, C 0/3. Main claim faithfulness B 9/11, C 3/5. C exact required refusals 2/2.
- Part 4 receipt: **11/12 checks pass**, overall incomplete solely because no C answer in the main comparison or sweep meets correctness, support and citation requirements. No passing score was substituted.
- Genuine capture inventory: **25 PNGs**, all 22 individual outcomes plus setup/retrieval/evaluation; 11 manifest checks pass. Nine images received visual inspection, recorded in `../screenshots/part4/scored-20260928-03/visual_review.json`.
- Analysis: **417 words**, counted only between the designated markers.
- One preliminary receipt detected an evaluation-export timing mismatch after a final evaluator reason was clarified. The old receipt/export remain under `raw/part4/setup/`; regenerating the derived CSV from the final judgments resolved consistency without changing any model output or score.

Owned Ollama PID 90820 was verified as `ollama serve` and stopped after delivery experiments. Port 11434 had no remaining listener. Model files/caches remain; reproduction needs an owned local service restarted with the commands above. [Cleanup receipt](../raw/part4/setup/service_cleanup.json). The [preservation audit](preservation_audit.json) confirms unchanged HEAD/branch/staging, exact prior-content prefixes in the three appended shared reports, and byte-identical earlier tracked application/evidence files, including Parts 1–3 verification.
