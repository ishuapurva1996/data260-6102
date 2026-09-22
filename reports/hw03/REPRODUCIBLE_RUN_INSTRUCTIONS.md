# Reproduce the application, retrieval results and report

Run commands from the repository root. Python 3.12 is recommended; the recorded runtime was 3.12.14 on macOS arm64. Web and retrieval dependencies use separate environments. No API key or hosted model is needed.

The current report uses retrieval run `manual-screenshots-20260921` and the screenshots supplied by Pragya Apurva in `screenshots/manual/`. The original `baseline-20260920` run and automated browser evidence remain unchanged. The new run produced identical hits and vectors, with new search timings.

## Prepare environments

```bash
python3.12 -m venv .venv-web
.venv-web/bin/python -m pip install -r requirements.txt
.venv-web/bin/python scripts/run_hw03_web.py --prepare-cert

python3.12 -m venv .venv-retrieval
.venv-retrieval/bin/python -m pip install -r requirements-retrieval.txt
.venv-retrieval/bin/python code/retrieval_compare.py download-model
```

Installation and `download-model` need network access. The latter downloads the pinned public embedding model into ignored `.venv-retrieval/model-cache`; `HW3_MODEL_CACHE` can override that location. Later evaluation uses local cached files, the CPU and one PyTorch thread. Keep the self-signed TLS certificate and key in ignored `tmp/https`.

- [Authentication setup and automated tests](part1/REPRODUCIBLE_RUN_INSTRUCTIONS.md)
- [Retrieval setup and rerun instructions](part2/REPRODUCIBLE_RUN_INSTRUCTIONS.md)

## Run authentication and capture the browser

```bash
.venv-web/bin/python scripts/run_hw03_web.py --host ::1 --port 8702
```

Leave the server running and open `https://[::1]:8702/`. The browser displays a warning for the self-signed certificate. The demonstration login is `admin` / `password`. Capture the signed-out homepage, empty login form, invalid login, successful dashboard, signed-in homepage and homepage after logout. The recorded images are `01-home.png` through `06-after-logout.png` in `screenshots/manual/`.

In a second Terminal tab, print the real login response headers, redacting the cookie value:

```bash
curl --noproxy '*' --cacert tmp/https/cert.pem \
  --silent --show-error --dump-header - --output /dev/null \
  --data 'username=admin&password=password' \
  'https://[::1]:8702/login' \
  | sed -E 's/(session=)[^;]*/\1[REDACTED]/'
```

The response should show HTTP 303, `location: /dashboard`, and `HttpOnly`, `Secure` and `SameSite=lax` cookie attributes. `07-cookie-header.png` records this check.

The capture helpers make requests to the running HTTPS server and use the local certificate:

```bash
.venv-web/bin/python reports/hw03/raw/manual-captures/capture_session_checks.py logout
.venv-web/bin/python reports/hw03/raw/manual-captures/capture_session_checks.py idle
ls -l code/web_application/templates
```

The logout check saves a cookie, logs out and attempts to reuse the same cookie. The idle check uses the normal **300-second** session limit and waits **301 seconds** without requests before retrying. Keep the server and Mac awake during the wait. Both checks should show HTTP 200 before expiry or logout, then HTTP 303 to `/login` when the saved cookie is reused. The actual Terminal captures are `08-logout-replay.png`, `09-idle-timeout.png` and `10-templates-directory.png`. The [capture manifest](raw/manual-captures/capture-manifest.json) records filenames, hashes and provenance.

The older automated authentication suite used a separate 2-second timeout for its fast expiry check. That historical test is distinct from the 301-second wait shown in the current report.

## Run automated authentication tests

Stop the manual server with Control-C before running browser suites on the same port:

```bash
.venv-web/bin/python -m pytest tests/test_api.py tests/test_hw03_auth.py tests/test_hw03_integration.py -q
npm install --package-lock=false
npx playwright install chromium
node tests/browser_part2.cjs
node tests/browser_hw03_auth.cjs
```

`browser_part2.cjs` checks the retained rental application, not document retrieval. The authentication browser suite starts and stops its own HTTPS processes and checks desktop/mobile behavior and copied-cookie rejection. These commands refresh `raw/part1/` and `screenshots/part1/`; they do not replace the manually captured images. Keep complete cookie values and signing secrets out of saved evidence.

## Verify the saved retrieval results

```bash
.venv-retrieval/bin/python -m pytest tests/retrieval -q
.venv-retrieval/bin/python code/retrieval_compare.py check-inputs
.venv-retrieval/bin/python code/retrieval_summarize.py \
  --run-dir reports/hw03/raw/part2/manual-screenshots-20260921 --check
.venv-retrieval/bin/python reports/hw03/part2/check_evidence_corruption.py \
  --run-dir reports/hw03/raw/part2/manual-screenshots-20260921 \
  --output /tmp/hw3-evidence-corruption.json
```

The saved run contains 15 question/method comparisons and 150 timed searches. The summarizer and default verifier need no network or embedding rerun. The corruption checker uses temporary copies to confirm that damaged evidence is rejected. The output path above preserves earlier verification receipts.

The input commit `08bd6e0495ce03281aa8fab7f70ac0b51e1c1442` precedes both the original experiment and the new run at `85a6dd8f2dfe2a89a8301a3accc8aef4d533c443`. The new run's `baseline_comparison.json` records unchanged full hits and vector sidecars; `annotations.json` records Codex's review of the returned passages. See the Part 2 guide to create another run with a new ID. Existing run directories cannot be overwritten.

## Run combined verification

```bash
python3 scripts/verify_hw03.py \
  --run-dir reports/hw03/raw/part2/manual-screenshots-20260921 --smoke
```

The orchestrator invokes the web verifier with `.venv-web/bin/python` and the retrieval verifier with `.venv-retrieval/bin/python`. It writes `reports/hw03/verification.json` and a new timestamped receipt directory under `raw/integration/`. Supply `--web-python`, `--retrieval-python`, `--receipt-dir` or `--output` to change those locations. `--smoke` checks the cached embedding model; omit it for saved-evidence verification.

A pass requires successful part checks, committed runtime source, preserved experiment ancestry and matching saved hashes. The web verifier reruns web/API tests and refreshes `raw/part1/self-check-pytest.txt`. This command does not rerun the browser captures or full retrieval test suite. Pass `--run-dir` explicitly because the script's default points to the original baseline.

## Build and check the report

Edit the narrative in `scripts/build_hw03_report.py` or its inputs, then regenerate the PDF. Editing generated `report.md` alone does not change the PDF.

```bash
python3.12 -m venv .venv-report
.venv-report/bin/python -m pip install -r requirements-report.txt
.venv-report/bin/python scripts/build_hw03_report.py \
  --code-ref 96b04abc04bb4cde131958ba38f37116336a4442 \
  --code-tag hw3-code \
  --upload-copy ../../Apurva_HW3.pdf
```

The tested-code tag identifies the integrated runtime checks. The new retrieval run separately records its execution commit in `run.json`; its experiment code and inputs match the earlier run. The build manifest records the PDF, Markdown and consumed-input hashes. Assembly uses saved local inputs and requires passing integration receipts. Installation needs network access.

The report uses the supplied browser and Terminal images under `screenshots/manual/`. Do not run the old report-viewer capture scripts to replace these images: those scripts produce a different presentation of saved evidence. Preserve the raw screenshots and their manifest when rebuilding. Review every rendered page for image readability, captions and page breaks.

After building:

```bash
python3 scripts/verify_hw03.py \
  --run-dir reports/hw03/raw/part2/manual-screenshots-20260921 \
  --require-report --smoke
```

`--require-report` checks required files, PDF markers, manifest hashes and tested-code ancestry. It does not inspect the page layout. Keep the visual review result in the run log. Avoid using a subsequently rewritten `verification.json` as a report input, which would create a hash cycle.

The repository PDF is `reports/hw03/report.pdf`; the external upload copy is `Apurva_HW3.pdf`. Their SHA-256 hashes must match after each revision. GitHub publication and course-portal upload are separate from local rebuilding and verification; the [submission checklist](SUBMISSION_CHECKLIST.md) records those steps.
