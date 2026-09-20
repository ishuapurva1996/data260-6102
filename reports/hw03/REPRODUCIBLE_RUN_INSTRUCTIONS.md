# Reproduce and verify the integrated HW3 submission

Run commands from this Git repository's root. The local review checkout is `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW3/worktrees/integration`. Python 3.12 is recommended; the recorded runtime was 3.12.14 on macOS arm64. Part 1 and Part 2 have separate environments. No API key, hosted model, or paid service is needed.

The report identifies the tested local code commit. Final tags, GitHub publication, collaborator access confirmation, and course upload are deliberately pending student review. Inspect `verification.json` and `RUN_LOG.txt` for what was actually run; a command listed here is not itself execution evidence.

## Prepare environments

```bash
python3.12 -m venv .venv-web
.venv-web/bin/python -m pip install -r requirements.txt
npm install --package-lock=false
npx playwright install chromium
.venv-web/bin/python scripts/run_hw03_web.py --prepare-cert

python3.12 -m venv .venv-retrieval
.venv-retrieval/bin/python -m pip install -r requirements-retrieval.txt
.venv-retrieval/bin/python code/retrieval_compare.py download-model
```

Installation and `download-model` need network access. The latter downloads the pinned public sentence-embedding model into ignored `.venv-retrieval/model-cache`; `HW3_MODEL_CACHE` can override that location. Evaluation subsequently requires local cached files and runs on CPU with one PyTorch thread. Part 2 dependencies must not be installed into the web environment. Existing ignored environments may be reused if their versions match the recorded requirements.

The self-signed TLS certificate/key stay in ignored `tmp/https`; do not commit keys or alter OS trust. `npm install --package-lock=false` retains the existing repository lockfile policy. See the two part guides for exact recorded package/runtime details and host-specific bundled executable paths:

- [Part 1 guide](part1/REPRODUCIBLE_RUN_INSTRUCTIONS.md)
- [Part 2 guide](part2/REPRODUCIBLE_RUN_INSTRUCTIONS.md)

## Run and verify authentication

```bash
.venv-web/bin/python scripts/run_hw03_web.py --host ::1 --port 8702
```

Visit `https://[::1]:8702/`; public demonstration credentials are `admin` / `password`. A manual browser shows a self-signed-certificate warning. Test login, Dashboard, Logout, and the retained rental form. The default inactivity limit is 300 seconds. Stop this server with Ctrl-C before running the suite below. If another process owns the port/address, leave it alone; choose the other documented loopback address when free.

Commit changed runtime/test source locally before collecting authoritative browser evidence. Run the following only when intentionally refreshing Part 1 evidence:

```bash
.venv-web/bin/python -m pytest tests/test_api.py tests/test_hw03_auth.py tests/test_hw03_integration.py -q
node tests/browser_part2.cjs
node tests/browser_hw03_auth.cjs
```

`browser_part2.cjs` is the retained **HW2 rental regression suite**, not HW3 retrieval. The HW3 auth suite starts and stops only its own HTTPS processes, exercises desktop/mobile behavior and copied-cookie rejection, and uses a separate 2-second idle-expiry demonstration. It refreshes `raw/part1/` and `screenshots/part1/`; inspect the new images and preserve timestamped console logs. The normal source default stays 300 seconds. Signing secrets and complete cookie values must not appear in committed evidence.

## Verify the existing retrieval experiment

```bash
.venv-retrieval/bin/python -m pytest tests/retrieval -q
.venv-retrieval/bin/python code/retrieval_compare.py check-inputs
.venv-retrieval/bin/python code/retrieval_summarize.py \
  --run-dir reports/hw03/raw/part2/baseline-20260920 --check
.venv-retrieval/bin/python reports/hw03/part2/check_evidence_corruption.py \
  --output /tmp/hw3-evidence-corruption.json
```

The saved baseline is the original 15 measured comparisons. The summarizer and default evidence verifier require no network or embedding rerun. The corruption checker makes temporary copies and confirms intentionally damaged evidence is rejected; it does not alter the baseline. The command above writes its new receipt to `/tmp/hw3-evidence-corruption.json`, preserving the original recorded negative-check receipt. Copy the new receipt into a distinct integration evidence directory if retaining that rerun. Preserving merge ancestry proves that corpus/questions/settings commit `08bd6e0495ce03281aa8fab7f70ac0b51e1c1442` preceded measured-code commit `cc0a57bae6e19778021643bffebf5c66d5e7c0a3`.

If deliberately repeating the experiment, use a new run ID and the instructions in the Part 2 guide. Existing run directories cannot be overwritten. Do not replace the original measured result merely because the two parts were merged. Changed experiment code or inputs requires new evidence and an updated explanation.

## Run aggregate verification

After committing the integrated source and running the appropriate suites:

```bash
python3 scripts/verify_hw03.py --smoke
```

The standard-library orchestrator invokes the Part 1 verifier with `.venv-web/bin/python` and the Part 2 verifier with `.venv-retrieval/bin/python`. It writes `reports/hw03/verification.json` and a fresh timestamped directory beneath `raw/integration/`. Each directory retains both part JSON receipts and captured stdout/stderr. Supply `--web-python`, `--retrieval-python`, `--receipt-dir`, or `--output` to override those locations. Receipt directories must be new, preventing accidental replacement of prior receipts. `--smoke` explicitly checks the real cached embedding model; omit it for evidence-only Part 2 verification.

A passing result requires successful subprocess exits, passing part payloads, committed current source, preserved experiment history, and unchanged measured retrieval runtime. A later hardening change to the Part 2 verifier is distinguished from the unchanged retrieval runtime that produced the baseline. The Part 1 subprocess reruns web/API tests and refreshes `raw/part1/self-check-pytest.txt`. The aggregate command does not rerun browser captures or the full retrieval test suite.

## Assemble and check the report

The report build script uses the source sections, screenshots, AI-use answers, and measured results to produce `report.pdf`, a generated Markdown reference (`report.md`), and `report-build.json`. The builder and generated report package remain uncommitted during disclosure review. Edit the narrative in `scripts/build_hw03_report.py` or its input files and regenerate; editing the generated Markdown alone does not change the PDF.

```bash
python3.12 -m venv .venv-report
.venv-report/bin/python -m pip install -r requirements-report.txt
.venv-report/bin/python scripts/build_hw03_report.py \
  --code-ref 96b04abc04bb4cde131958ba38f37116336a4442 \
  --upload-copy ../../Apurva_HW3.pdf
```

The optional upload destination may be any chosen path outside the repository; the current working copy uses the assignment's `HW3/Apurva_HW3.pdf` location. The recorded build used the bundled document runtime with the same pinned packages. Installation needs network; assembly itself uses only saved local inputs. The code reference above matches the completed integration checks in `raw/integration/checks.json`. If runtime source changes, commit and rerun affected checks, then use the resulting verified reference instead of silently relabeling old evidence. Later documentation and verifier-only commits do not change the runtime that produced these checks.

The manifest records the tested-code commit, PDF and Markdown hashes, consumed source hashes and page count. It requires successful integration receipts before generating the report. Final visual review is a separate step.

The saved report figures can be reused. If deliberately refreshing their presentation, run `node scripts/capture_hw03_report_evidence.mjs` for browser views of the original retrieval output, and `node scripts/capture_hw03_auth_report.cjs` for three new mobile viewport captures plus saved-header/directory viewers. The latter starts and stops its own local HTTPS server and refuses an occupied `::1:8702`; it does not alter or replace the original 27-check browser evidence. Both scripts save input hashes and screenshot receipts under `raw/integration/`. Regenerate the report after any figure changes.

After building and visually checking every page:

```bash
python3 scripts/verify_hw03.py --require-report --smoke
```

`--require-report` checks the required shared files, PDF file markers, manifest hashes and tested-code ancestry. It does **not** claim to render the PDF or judge visual quality. Keep the actual page inspection result separately in the integration log/evidence. Build inputs should not include a subsequently rewritten aggregate `verification.json`, which would create a freshness cycle.

The submission PDF inside Git is `reports/hw03/report.pdf`. The external upload copy is `Apurva_HW3.pdf`; compare its SHA-256 with the repository copy after every report revision. Local commits save review checkpoints. Do not push, create final tags, or submit until the student approves the package.
