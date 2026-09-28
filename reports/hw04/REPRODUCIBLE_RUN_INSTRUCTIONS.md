# Reproduce HW4

Run commands from the repository root. Use Python 3.12, Node.js 22.12 or newer,
and MySQL 8.4. Private credentials, TLS keys, environments and model caches stay
outside tracked submission files. The selected outputs are already saved; new
experiments must use new output directories.

## Parts 1–3 application and measurements

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python scripts/run_hw04_web.py --env-file /absolute/path/to/private-ordinary.env
```

The private file supplies `HW4_DATABASE_URL`, `HW4_SEED_EMAIL`, and
`HW4_SEED_PASSWORD`; setup also uses `HW4_SEED_NAME`. Prepare a new database
using [HW4_DATABASE.md](../../docs/HW4_DATABASE.md) before starting. Do not run
migrations or seed commands against a database holding the recorded experiment.
The launcher serves React and the authenticated API at
`https://127.0.0.1:8702/` and creates a local self-signed certificate if needed.

The ordinary application and performance experiment use distinct MySQL
instances, both with database `s6102_rel`. The performance instance contains
5,000 rentals and 200 managers. The
[Part 3 guide](../../scripts/hw04/part3/README.md) documents its ownership checks,
seeding, benchmark, index experiment and Postman collection. A reproduction
requires a new dedicated instance and new evidence directories; preserve the
selected attempt below.

Recompute the summary from the saved 180 requests without database access:

```sh
.venv/bin/python scripts/hw04/part3/summarize.py \
  --raw reports/hw04/raw/part3/attempts/20260928T003859.945761Z-cd277c20/requests.jsonl \
  --output-dir /tmp/hw4-part3-summary-review
```

## Part 4 saved evidence and new runs

The selected run is `reports/hw04/raw/part4/scored-20260928-04`. It retains the
frozen inputs, retrieved text/source/score printouts, raw model requests and
answers, comparison, top-k sweep and evaluation tables. The corpus manifest
references four preserved HW3 documents plus the fifth Part 4 document.

For an independent environment:

```sh
python3.12 -m venv .venv-rag
.venv-rag/bin/python -m pip install -r requirements-rag.txt
.venv-rag/bin/python scripts/verify_hw04_part4.py \
  --run reports/hw04/raw/part4/scored-20260928-04 \
  --report reports/hw04/part4/REPORT_SECTION.md \
  --output /tmp/hw4-part4-evidence-review.json
```

This check uses saved records and judgments; it makes no model call and does
not independently establish that a model answer is correct.

A new experiment needs local Ollama with pinned `qwen2.5:3b` and `qwen2.5:7b`
models, the MiniLM embedding cache, and both pinned tokenizer caches. Exact
digests and setup commands are in [part4/HANDOFF.md](part4/HANDOFF.md). Its older
report/capture instructions are historical; use the final report sources
described below. With those assets prepared, choose a new directory:

```sh
.venv-rag/bin/python code/rag.py run \
  --config reports/hw04/raw/part4/scored-20260928-04/frozen/experiment_config.json \
  --output reports/hw04/raw/part4/reproduction-01
```

The command produces 22 final answers and eight auxiliary clarification
decisions. A new run requires its own evaluation of its actual answers; do not
copy the selected run's judgments onto it. Fixed seeds do not promise identical
outputs across hardware or model versions.

## Submission verification

Check the saved evidence offline:

```sh
.venv/bin/python scripts/verify_hw04_submission.py --prepare
```

This writes `reports/hw04/raw/report-finalization/preparation.json`. An optional
`--output` can select another JSON beneath that directory. Preparation checks
the saved Parts 1–3 receipt, the original 180 benchmark rows, and selected Part 4
evidence. It starts no server and creates no final tagged success receipt.

For the exact tagged smoke test, check out `hw4` with no changed submission
files. Build React and ensure `tmp/https/cert.pem` and `tmp/https/key.pem` exist
from `scripts/run_hw04_web.py --prepare-cert`. Port 8702 must be free. Supply the existing ordinary and
performance database environments explicitly:

```sh
.venv/bin/python scripts/verify_hw04_submission.py --tagged \
  --ordinary-env /absolute/path/to/private-ordinary.env \
  --performance-env /absolute/path/to/private-performance.env
```

`HEAD` must equal `hw4`. The verifier rejects uncommitted submission changes;
only root `verification.json` and generated receipts under
`reports/hw04/raw/report-finalization/` are exempt. Both private files must name
distinct loopback MySQL instances with existing accounts and database
`s6102_rel`. The performance database must retain the 5,000-rental/200-manager
dataset. The verifier does not seed, migrate, reset, or run another benchmark.

The smoke test starts each HTTPS instance in turn, checks authentication,
ordinary reads, built React pages/assets, equal naive/fixed data at all three
page sizes, SQL statement counts, and logout cleanup. It verifies source hashes
before and after execution and stops only its own servers. It makes no model
calls or rental CRUD requests; login and logout perform normal session writes.

Only a complete pass writes repository-root `verification.json`. Failures write
a separate timestamped receipt under `raw/report-finalization/`. Read the
receipt's commit, status and individual checks; a filename alone is not proof.

For publication, `hw4-code` identifies the committed code/evidence baseline and
`hw4` identifies the approved final code/report package. Run the smoke test at
that immutable `hw4` revision, then commit its generated receipt on `main` in a
following commit with no application or report changes. Keep the tested tag at
the commit recorded in the receipt. This sequence documents the tested source
without pretending the later receipt commit was the executed revision.

## Report preservation

[report.pdf](report.pdf) and [Apurva_HW4.pdf](Apurva_HW4.pdf) are identical
79-page copies. [report-build.json](report-build.json) records the original
screenshots and their placement. All final figures use `screenshots/user/`
without cropping or reconstructed panels. `screenshots/part4/` contains older
saved-output views, not final report inputs. Preserve the approved PDF and
original image bytes when checking the package; do not run historical capture
tools to replace them.

Earlier homework reports and tags remain historical snapshots. Their runtime
assumptions may differ from HW4, so do not overwrite their evidence with current
application results.
