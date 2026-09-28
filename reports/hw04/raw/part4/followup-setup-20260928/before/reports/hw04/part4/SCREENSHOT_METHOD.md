# Part 4 screenshot method

`scripts/capture_hw04_part4.cjs` opens local evidence pages in real Chromium through Playwright and saves full-page PNG screenshots. Every page is headed **Saved local experiment output — browser capture**. These are browser captures of saved local CLI experiment records, not screenshots of a live terminal or a model chat application.

The tool reads the selected run's raw `responses.jsonl`, `RUN_LOG.txt`, frozen configuration and source manifest, chunk/index audit, and evaluation `summary.json`. It creates one separate page for every one of the 22 model responses, plus corpus/index/chunk, retrieval-before-generation, and evaluation pages. The six sweep references explicitly reuse the unchanged main k=3 images.

Raw answers and application prompts are inserted as escaped text without rewriting, Markdown conversion, or clipping. When raw Ollama mode is used, the exact wire prompt is also shown. Code excerpts come from that run's frozen sources, include original line numbers, and sit immediately above the corresponding output. Evaluation code, which is written after generation, is taken from a frozen copy when one exists; otherwise the tool saves an explicitly labeled evaluation-time snapshot beside its screenshots.

The screenshot directory contains HTML, PNGs, and a `manifest.json` with source hashes, screenshot hashes, evidence mappings, response IDs, browser version, capture times, image dimensions, code lines, and render checks. The tool checks displayed raw text against the saved records and rejects horizontal overflow. A new output directory is required to prevent replacing an earlier evidence set. It does not alter the raw run, call a model, or connect to the application or database. Visual inspection of representative PNGs remains a separate recorded review step.

Reproduction command (replace the run and screenshot directory with the selected evidence names):

```sh
cd '/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend'
'/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node' scripts/capture_hw04_part4.cjs --run reports/hw04/raw/part4/SELECTED-RUN --output reports/hw04/screenshots/part4/NEW-CAPTURE-DIRECTORY
```

The default Playwright package is `/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`; `HW04_PLAYWRIGHT_PATH` can point to another installed copy. Capture execution should occur only after the final experiment and evaluation artifacts are complete.
