# Screenshot provenance

The five PNG files in `../screenshots/part2/` are full-page screenshots taken by Playwright in an actual headless Google Chrome process. They show browser pages generated from the saved baseline output, not a simulated terminal or generated image. `build_evidence_view.py` embeds exact Q1 stdout excerpts for the three methods, renders measured summary values, and displays the complete Q2/token rank-1 passage with its separately labelled gold answer and review.

`capture_evidence.mjs` saves browser version, UTC capture timestamp, viewport, dimensions, overflow checks, HTML hashes and PNG hashes in `screenshot_capture.json`. All five pages were visually inspected: text is readable, the query dimensions/first eight values/vector shapes/rank tables are visible, and nothing is clipped. The metrics and high-score-failure pages match the saved artifacts. The code excerpts abbreviate the corresponding implementation with fixed frozen parameter values; full source remains in `src/retrieval/`.

Recreate the evidence pages with:

```bash
python3 reports/hw03/part2/build_evidence_view.py
```

Then use an installed Playwright/Chromium environment:

```bash
node reports/hw03/part2/capture_evidence.mjs
```

The original environment used the bundled Node/Playwright runtime and system Chrome, selected with `HW3_PLAYWRIGHT_MODULE` and `HW3_BROWSER_PATH`. Chrome launch was blocked by the filesystem/process sandbox on the first attempt; an approved escalation then captured the pages. No retrieval rerun was needed for the screenshots, and no image was edited after capture.
