# HW4 Part 4 focused follow-up handoff

The focused follow-up is complete locally. The new full run preserves **22 final answers plus eight auxiliary clarification decisions**. C now gives a complete, supported, cited Q3 answer, appropriately clarifies Q4, and exactly refuses Q5/Q6. That successful cited answer satisfies **our reviewed plan's completion criterion**, not an explicit assignment minimum. Q1/Q2 remain failures and are retained. Student semantic review and later whole-homework assembly remain separate work.

## Checkout and selected evidence

- Worktree: `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend`
- Branch: `codex/hw4-part2-backend`; unchanged HEAD `421c77ddca9ce998e5088dd305ea4da9bb714238`.
- Selected run: `reports/hw04/raw/part4/scored-20260928-04/`, started `2026-09-28T05:48:33.227083+00:00`, finished `2026-09-28T05:50:01.978836+00:00`.
- Development: `reports/hw04/raw/part4/development-followup-integrated-01/`; its `gate_assessment.json` records two supported cited answers and eight appropriate context-dependent behaviors. It was assessed at `05:47:48 UTC`, before the `05:48:33 UTC` freeze. D2/D3 safe refusals remain retrieval/full-corpus answer failures. D7's clarification is appropriate but awkwardly phrased.
- Configuration: [experiment_config.yaml](experiment_config.yaml); development rationale and embedded assessment: [calibration.json](calibration.json). [FOLLOWUP_DIAGNOSIS.md](FOLLOWUP_DIAGNOSIS.md) retains every failed follow-up probe, interpretation and limitation. The clarification classifier and prose rule were selected using development questions only.
- Selected `run_metadata.json` records identities, dirty state and exact code/input hashes. `frozen/` retains configuration, source texts, code, gold questions, calibration and model provenance. Runtime uses imported live code and frozen data; matching start/end hashes identify the executed code. No live generation input changed during the run.
- `requests.jsonl`, `responses.jsonl`, `retrievals.jsonl`, `RUN_LOG.txt`, `retrieved_chunks.txt`, `routing_requests.jsonl` and `routing_responses.jsonl` preserve actual prompts, retrievals, timings and unedited raw model outputs. `evidence_hashes.json` covers generation artifacts. No old answer was substituted, even where deterministic A/B outputs match the prior run exactly.
- `judgments.json` contains identified assistant semantic judgments and exact supplied support quotes. `evaluation.csv`, `comparison.csv`, `k_sweep.csv`, `evaluation_summary.csv` and `summary.json` are derived tables. Semantic correctness is not established by a passing unit test or hash check.
- Report: [REPORT_SECTION.md](REPORT_SECTION.md). Receipt: [verification.json](verification.json). Genuine capture inventory: [manifest](../screenshots/part4/scored-20260928-04/manifest.json); [visual review](../screenshots/part4/scored-20260928-04/visual_review.json); [method](SCREENSHOT_METHOD.md).
- Follow-up setup and logs: `reports/hw04/raw/part4/followup-setup-20260928/`. Its `before/` directory preserves the prior current report, handoff, receipts, source and shared-report state. All three earlier scored runs and all earlier screenshots remain in their original directories.

## Implementation and findings

The final answer prompt explicitly requests complete sentences, coverage of every question part, and supporting citation numbers; it states that a citation alone is not an answer. The original `[1]` failure was reproduced on a separate disclosure-retention development question. Both raw outputs reported a normal stop after four tokens, with ample capacity. The prose change repaired that development case without inserting answer facts.

C now first asks a local 7B model whether the question is specific enough for lookup. It receives no retrieved text, question ID, history or gold key. A `CLARIFY` route sends an evidence-free clarification prompt to the common 3B final-answer model. `CLEAR` uses the normal filtered/labeled grounding prompt. Invalid or incomplete classifier outputs are saved and stop the run; there is no silent fallback or canned final answer. Routing requests and responses are saved separately, and C's end-to-end time includes their cost.

All A/B/C final answers remain on the same 3B model and settings. The 7B model is an additional classifier only for C, so this is a comparison of complete configurations, not a causal estimate of one prompt sentence. Using 7B for final answers failed a development deadline question. General dense/BM25 fusion and one local cross-encoder trial did not retrieve that deadline in their top three, so neither was adopted. The optional `hybrid.py` helper and its tests remain available as a documented rejected experiment; selected retrieval is unchanged dense cosine.

## Environment and caches

Dedicated environment: `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend/.venv-rag`, Python 3.12.13. Hardware: Apple M4, 24 GiB RAM, macOS 15.7.4. Dependencies remain `requirements-rag.txt`; exact lock is `reports/hw04/raw/part4/setup/requirements-rag.lock.txt`. Existing application/model environments were preserved.

- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; cache `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend/.cache/hw04-rag/embeddings`.
- Common final-answer model: Ollama 0.33.0 `qwen2.5:3b`, Q4_K_M, digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`.
- C's auxiliary classifier: `qwen2.5:7b`, digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`.
- Ollama model store: `/Users/pragyaapurva/.ollama/models`. Public downloads are setup operations; inference uses loopback only with cloud disabled.
- Final-answer tokenizer: `Qwen/Qwen2.5-3B-Instruct`, revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`.
- Auxiliary tokenizer: `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`.
- Shared explicit tokenizer cache: `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend/.cache/hw04-rag/generator-tokenizer`. Tokenizer and actual model-file hashes are retained in `setup/model_assets_qwen25.json` and `followup-setup-20260928/model_assets_qwen25-7b.json`, with matching tokenizer records.
- Rejected optional reranker asset cache: `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend/.cache/hw04-rag/reranker`; `cross-encoder/ms-marco-MiniLM-L6-v2`, revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`. It is **not needed for selected-run reproduction**. Its pinned files and eight actual development retrievals remain evidence.

Fixed settings: temperature 0, seed 6102, `think:false`, 4096 context tokens, 768 maximum output tokens, main k=3, Q2 sweep k=1/3/5, 500-character maximum chunks, 50-character overlap, relevance cutoff 0.50, maximum C evidence 1800 generator tokens, and 128-token template margin. No source text is silently truncated. Both model roles use the same generation options and independent requests.

## Exact reproduction commands

Run from the existing checkout. Every generation/capture command requires a **new directory** and refuses to overwrite existing evidence. Fixed seeds do not guarantee cross-hardware or cross-version identity; any new outputs need their own semantic review.

```sh
cd '/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend'
.venv-rag/bin/python -m pytest -q tests/test_hw04_rag.py tests/test_hw04_rag_evaluation.py tests/test_hw04_rag_hybrid.py
.venv-rag/bin/python -m py_compile code/rag.py src/rag/pipeline.py src/rag/runner.py src/rag/hybrid.py src/rag/evaluation.py scripts/verify_hw04_part4.py
```

If the dedicated environment is missing, build a new one without replacing any existing application environment:

```sh
uv venv --python 3.12 .venv-rag-reproduction
uv pip install --python .venv-rag-reproduction/bin/python -r reports/hw04/raw/part4/setup/requirements-rag.lock.txt
```

Use that new environment's Python instead of `.venv-rag/bin/python` below if needed. The documents are already retained. Only if pinned public model/tokenizer assets are missing:

```sh
.venv-rag/bin/python code/rag.py download-model
.venv-rag/bin/python code/rag.py download-tokenizer
.venv-rag/bin/python code/rag.py download-tokenizer --config reports/hw04/raw/part4/followup-setup-20260928/development-config-7b.json
```

Start an owned local Ollama service in another terminal only if port 11434 is free; do not replace an unrelated listener:

```sh
OLLAMA_NO_CLOUD=1 OLLAMA_NOPRUNE=1 ollama serve
```

If missing, download `ollama pull qwen2.5:3b` and `ollama pull qwen2.5:7b`. Public tags may move; the runner rejects a digest different from the pins above. Do not silently accept a different model. With the owned service available:

```sh
.venv-rag/bin/python code/rag.py inspect --output reports/hw04/raw/part4/reproduction-development-followup-01
.venv-rag/bin/python code/rag.py pilot --output reports/hw04/raw/part4/reproduction-pilot-followup-01
.venv-rag/bin/python code/rag.py run --config reports/hw04/raw/part4/scored-20260928-04/frozen/experiment_config.json --output reports/hw04/raw/part4/reproduction-scored-followup-01
```

`inspect` builds/audits the real index and development retrievals without generation. `pilot` makes eight development final answers and eight auxiliary classifier calls. `run` makes 18 main final answers plus four distinct sweep answers and eight auxiliary calls: **30 local generation calls total**. Main k=3 results are referenced, not regenerated, in the six-row sweep. Retrieval text/source/score is printed before model calls. The selected source/code/configuration should remain unchanged for this reproduction; frozen copies are the historical authority if later live development occurs.

A new run needs a new manually authored `judgments.json` based on its actual outputs and evidence, using the unchanged schema in `src/rag/evaluation.py`. Do not transfer the selected judgments onto new answers. To recompute only the selected derived tables without generation:

```sh
.venv-rag/bin/python - <<'PY'
from src.rag.evaluation import write_evaluation
write_evaluation('reports/hw04/raw/part4/scored-20260928-04')
PY
```

Capture real browser views into a new directory:

```sh
'/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node' scripts/capture_hw04_part4.cjs --run reports/hw04/raw/part4/scored-20260928-04 --output reports/hw04/screenshots/part4/reproduction-followup-capture-01
```

Bundled Playwright: `/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`. These PNGs are genuine Chromium screenshots of saved local records, clearly labeled as such. They are not live-terminal screenshots. The capture preserves exact answer/prompt text and shows auxiliary routing separately.

Re-render the current report to a **separate review copy** from the selected tables/capture inventory:

```sh
.venv-rag/bin/python reports/hw04/part4/experiments/render_followup_report.py scored-20260928-04 /tmp/hw04-part4-report-review.md
```

Offline verification to a fresh receipt:

```sh
.venv-rag/bin/python scripts/verify_hw04_part4.py --run reports/hw04/raw/part4/scored-20260928-04 --report reports/hw04/part4/REPORT_SECTION.md --output reports/hw04/part4/verification-reproduction-followup.json
```

Verification distinguishes automated evidence consistency from the plan's supported-answer/refusal demonstration assessed using saved assistant semantic judgments. It does not independently prove semantic truth. Auxiliary identity/token checks and the development-assessment-before-freeze chronology are included. Old unflagged runs retain their original 12-check path and recorded failures.

## Remaining work

Q1 still misses the 14-day passage. Q2 still misses the standalone inspection definition at k=1/3/5; no tested k yields a complete supported cited answer, and C k=1 omits citations. These model/retrieval limitations remain honest scored failures. They do **not** block the requested focused follow-up after the plan criterion and clarification/refusal demonstrations succeeded. Further retrieval research is optional and would need a separate development freeze and new full comparison.

Review the report and assistant claim-level judgments, especially Q2's unsupported inspection statement and Q3's citation support. Then, in a separately authorized task, integrate Parts 1–4 into the final homework PDF, place long screenshots readably, confirm submission/repository details, and perform any final tagged verification required by the course. No PDF assembly, Git history operation, deployment or database operation occurred here. Parts 1–3's saved 46/46 receipt is preserved historical evidence, not a rerun claim.

## Final verification results

- Focused suite: **65 passed in 1.04 seconds**, [test output](../raw/part4/followup-setup-20260928/tests-focused-final.txt). Compilation passed; [code review](../raw/part4/followup-setup-20260928/code_review.json) found no actionable defect in the selected generation path. Synthetic tests are separate from real model results.
- Matrix: **22/22 final answers and 8/8 auxiliary decisions** completed normally, with unchanged generation hashes and no live-input changes.
- Main semantic accuracy: **A 2/6, B 3/6, C 4/6**. C answerable accuracy **1/3**, faithful claims **4/5**, format **6/6**, robustness **3/3**, exact Q5/Q6 refusals **2/2**. B faithful claims **9/11**; A faithfulness is N/A.
- Receipt: **13/13** overall: **12/12 automated evidence-consistency checks** and **1/1 plan-completion check using saved semantic judgments**. A pass does not mean every answer is correct or independently establish semantic truth.
- Captures: **25 genuine PNGs**, **61 exact-text checks**, all overflow checks passed, and **nine actual images visually reviewed**. The initial sandbox Chromium launch failure is preserved; an approved local retry succeeded.
- Report analysis: **413 words**. Current report, tables, screenshots and handoff select scored04; all earlier scored runs and the former delivery snapshot remain retained.

Owned Ollama PID **96363** was verified as `ollama serve` and stopped after experiments; port 11434 had no remaining listener. Models and caches remain available. [Cleanup receipt](../raw/part4/followup-setup-20260928/service_cleanup.json). The [preservation audit](preservation_audit.json) records unchanged HEAD/branch/staging, all 469 prior raw/screenshot hashes, preserved shared-report prefixes and unchanged other tracked files. [Delivery manifest](delivery_manifest.json) hashes the current reviewable artifacts.
