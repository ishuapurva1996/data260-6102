# HW3 local review and final submission checklist

This checklist separates the local review package from later publication. Consult `verification.json` and `RUN_LOG.txt` for completed checks; unchecked items below are review tasks, not claims of failure.

## Local package to review

- [ ] Inspect the integrated Part 1 and Part 2 code and local commit history. Preserve the Part 2 input-freeze commit and its ancestry.
- [ ] Confirm the report's tested-code commit matches the code that was verified. No final tag is claimed during this review stage.
- [ ] Confirm current web/API/auth tests, rental browser regressions, auth browser checks, retrieval tests, input checks, summary regeneration, corruption checks, and aggregate verification passed.
- [ ] Read `reports/hw03/report.pdf`: six personal settings, hardware/model, repository link, Part 1 explanation/screenshots, Part 2 code/output/results, high-score failure, observations/conclusion, all four AI-use answers, and full auth.py at the end.
- [ ] Inspect every rendered PDF page: readable figures, complete code, working links, no clipped text, and sensible page breaks.
- [ ] Review the AI-use disclosure and correct any personal statements before submission.
- [ ] Confirm required shared files: `RUN_LOG.txt`, `AI_USE.md`, `verification.json`, `REPRODUCIBLE_RUN_INSTRUCTIONS.md`, `METRICS.md`, `SOURCES.md`, `CORPUS_MANIFEST.json`, and `questions.yaml`.
- [ ] Confirm raw results, source snapshots, source manifests, and screenshot evidence are present. Keep assignment/tutor files, planning notes, environments, model caches, TLS keys and credentials outside tracked submission files.
- [ ] Compare the external `Apurva_HW3.pdf` upload copy to `report.pdf`; they must have the same SHA-256.
- [ ] Request fixes if needed, rerun affected checks, rebuild/reinspect the report, and save additional local commits.

## Only after student approval

The following actions are intentionally pending. This local integration pass does not perform them.

- [ ] Decide the tested-code reference and update report provenance if needed.
- [ ] Create the assignment's required `hw3` tag on the complete approved submission. Any optional tested-code tag must be clearly distinguished.
- [ ] Push the approved branch/commits and chosen tags to the existing `data260-6102` GitHub repository.
- [ ] Open the published repository, report and tag links and verify the intended files are accessible.
- [ ] Verify collaborator access for `Sbnikitha` and `supriyaselvanganesan`; do not infer access from a requested or sent invitation.
- [ ] Upload `Apurva_HW3.pdf` to the course submission page and provide the repository link wherever requested.
- [ ] Confirm the course page records the intended uploaded file and successful submission.

The assignment does not require a separate ZIP, new HW3 repository, publicly hosted web application, or Docker build. Source code remains in the existing shared root folders; the homework evidence lives in `reports/hw03/`.
