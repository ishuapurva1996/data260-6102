# HW2 submission checklist

Prepared for Pragya Apurva, SID4 6102. Assignment source: `DATA260_HW2.pdf`, pages 1-6. The application extends HW1 in the same repository. This checklist separates completed local evidence from the remaining online submission steps.

## Exact submission items

1. Upload **Apurva_HW2.pdf** from the sibling `../HW2/` folder to the course submission portal. It is identical to `reports/hw02/report.pdf` in Git.
2. Provide the repository link: https://github.com/ishuapurva1996/data260-6102 . The same link appears in the PDF.
3. Keep the required report folder and the shared application source in the repository. Push the intended branch plus both local tags before submitting the link. No separate code ZIP is requested by the assignment PDF.

| Assignment requirement | Completed local item / evidence |
|---|---|
| Six personal values at report top | First page: SID4 6102, PORT_BASE 8702, PREFIX s6102, SEED 6102, VERIFY_SEED 266102, DOMAIN_ID 6 |
| Hardware, local model and tagged code hash | First page: M4 MacBook Air, 24 GB, macOS; qwen3:1.7b documented HW1 substitute; full hw2-code commit hash |
| Same repository and shared root code | `code/`, `src/`; historical HW1 preserved by its original tag, without a new application copy |
| Code with matching output screenshots | PDF pairs relevant code excerpts above actual UI or saved-output screenshots; complete code remains in Git |
| Part 1: 375px form/list | `screenshots/part1/`; real 375 x 812 images and no-overflow measurements in `raw/part12/capture-manifest.json` |
| Part 1: empty/loading/error | Separate PDF pages and screenshots; deliberate delay and controlled UI failure labeled accurately |
| Part 2 Q1: create and return home | New ID 3, actual POST 201, resulting list screenshot and GET snapshot |
| Part 2 Q2: update ID 1 and return home | Changed title/address, actual PUT 200, updated list; UI also supports editing any listing |
| Part 2 Q3: delete highest ID and return home | ID 3 removed, actual DELETE 204, final IDs 1 and 2 |
| Part 2 Q4: primary OR secondary search | Independent title-only Downtown and address-only Market matches; additional Clear/no-match captures |
| FastAPI on PORT_BASE | Read-only actual port-8702 screenshot, successful HTTP requests and live self-check |
| Part 3: typed state, workers, supervisor/router | `src/agent_graph/` code excerpts and current real normal-run output |
| Part 3: LangGraph wiring, stream and correction loop | Conditional-edge/stream code; real-model controlled always-issue Reviewer reaches ten-turn ceiling |
| Shared HW1 adapter and model | Nodes call through `src/model_client.py`; same documented qwen3:1.7b substitute |
| Part 4 Q1: Pydantic output rules | Exactly three string tags, 3-30 characters each, summary at most 25 words; valid real output shown |
| Part 4 Q2: error feedback and bounded retry | Actual graph repair with clearly labeled scripted responses; adversarial real failures show repeated bounded retries |
| Part 4 Q3: frozen input and 30 trials | `cases/schema_input.json`, frozen manifest, 30 raw records and four-category table: 30 / 0 / 0 / 0 |
| Part 4 Q4: 20 runs each at ceilings 2 and 10 | Separate raw cohorts; 100% completion in both, mean 2485.63 / 2472.25 ms; documented rule selects 10 |
| Part 4 Q5: adversarial input, five trials, why/fix | Frozen case; actual 5/5 ceiling exits due to short invalid tags; proposed trusted retry-message fix is explicitly not applied to baseline |
| Real console output and timestamps | `RUN_LOG.txt` combines preserved Part 1/2, Part 3, Part 4 and tagged-smoke output; final run in `RUN_LOG_SUBMISSION.txt` |
| Machine-readable experiment records | `raw/part4/20260914T0610-baseline/`: CSV, JSONL, JSON, input/source hashes and all raw model responses |
| Filled result tables | `METRICS.md` and the report; means recomputed from saved unrounded values |
| Four AI-use answers | `AI_USE.md` and report, including the student's stated extensive UI validations and logic checks |
| Reproducible instructions | `REPRODUCIBLE_RUN_INSTRUCTIONS.md` covers setup, application, checks, new campaigns and report rebuilding |
| Tagged objective smoke test | `scripts/verify_hw02.py` writes `verification.json`: identity, hash, model/configuration, seeds, individual pass/fail; source unchanged |

## Screenshot coverage and limitations

All required output categories have been captured; no additional screenshot is needed to fill a known gap. The assignment asks for code and corresponding output screenshots together. This report typesets actual code excerpts and places the output screenshot below; it does not rely on UI screenshots alone.

The 375px screenshots are original browser page captures, without browser chrome or a DevTools toolbar. Their real viewport and document widths are recorded. Part 3/4 panels are genuine browser screenshots of saved console/JSON/results, labeled as recorded output rather than native Terminal windows. Raw outputs are included so the displays can be checked.

The repeatable create/update/delete screenshots used isolated port 18702 to preserve a running 8702 server's records. Separate read-only evidence and a live smoke check confirm the required port 8702. Both use the same submitted web source. If the instructor specifically wants a visible native Terminal or DevTools window, those would be optional retakes beyond the wording of the PDF.

## Required user actions before submitting online

- [ ] Review the report and personal contribution wording in `AI_USE.md`; revise if needed. After edits, rebuild the PDF and regenerate verification/hashes.
- [ ] In GitHub, complete the identity confirmation and verify that **Sbnikitha** and **supriyaselvanganesan** appear as collaborators. The repository page opened successfully and was public, but the collaborator settings page requested identity confirmation. Public readability does not by itself confirm collaborator membership.
- [ ] Push the intended submission branch and `hw2-code` / `hw2` tags, then verify their contents remotely. These external actions were not performed during report preparation. If submitting through the default branch, merge the prepared branch through the user's chosen workflow first.
- [ ] Upload `Apurva_HW2.pdf` and provide the working repository link in the course portal.

## Tags and evidence integrity

`hw2-code` freezes the implementation and verifier at `6a076db1447f00a0097cfc16f5de460c37e65079`. The later `hw2` package tag includes generated report/evidence files with unchanged application and verifier bytes. Use the code tag for runtime provenance and the package tag for the complete submission. The PDF identifies the code tag because a generated file cannot embed the hash of its own containing commit.

`submission-manifest.json` records deliverable hashes; individual screenshot/campaign manifests retain deeper provenance. Historical measured runs keep their actual execution hash and dirty state rather than being relabeled as executions at the later tag. A passing local verification does not imply that GitHub pushes, collaborator access or portal upload are complete.
