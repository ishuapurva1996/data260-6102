# Parts 1 and 2 — actual image manifest

Unaltered PNG captures produced by Playwright page.screenshot in Chromium. No app DOM, styling, data response, or screenshot pixels are replaced or overlaid. Mutations use actual browser controls and real local HTTP requests.

Port 8702 was already occupied by an existing Python process. This capture owns a separate single-worker Uvicorn process on 18702, restarted between Parts 1 and 2. The existing process and its in-memory records were not modified. The submitted main.py default remains PORT_BASE=8702.

Headless Chromium screenshots contain page content only; browser chrome and DevTools width toolbar are absent. Each Part 1 original PNG is 375x812 at device scale factor 1. Metadata records the actual innerWidth and document scrollWidth; report captions must state the viewport explicitly. The capture port is an isolated verification port, not the assignment default.

Immediate home navigation prevented Playwright from retaining three POST/PUT response bodies; their actual HTTP statuses and request payloads are logged, and authoritative GET snapshots prove the stored records. DELETE 204 correctly has an empty body. Search GET response bodies are available. No mutation body is reconstructed or presented as a captured response.

Captured 2026-09-14T07:17:16.699Z through 2026-09-14T07:17:35.417Z; Chromium 151.0.7922.34, Playwright 1.62.1. HEAD 4b8875ac247168a3aa06464f735157d00bf97351; web source clean.

All 19 original screenshots were visually inspected. No horizontal overflow: mobile innerWidth/documentScrollWidth/bodyScrollWidth are all 375.

| File | Original pixels | Caption |
|---|---:|---|
| `reports/hw02/screenshots/part1/P1-01-empty.png` | 375 × 812 | At an actual 375 × 812 viewport, the empty store shows 0 listings and an explicit no-record message; highest-ID deletion is disabled. |
| `reports/hw02/screenshots/part1/P1-02a-form-upper.png` | 375 × 812 | Filled responsive create form at 375px width, upper fields. Single-line inputs may horizontally clip long values. |
| `reports/hw02/screenshots/part1/P1-02b-form-lower.png` | 375 × 812 | Filled responsive create form at 375px width, description, property type, terms, and reachable submit control. |
| `reports/hw02/screenshots/part1/P1-03-loading.png` | 375 × 812 | Controlled slowSave=true adds eight seconds before a real POST. Saving status and disabled controls are visible at 375px. |
| `reports/hw02/screenshots/part1/P1-04-list.png` | 375 × 812 | Actual 375px populated list with new ID 1, long email wrapping in the card, and reachable Edit/Delete controls. |
| `reports/hw02/screenshots/part1/P1-05-editor.png` | 375 × 812 | Supplemental 375px editor: ID 1 is prefilled and Save changes/Cancel remain reachable. |
| `reports/hw02/screenshots/part1/P1-06-error.png` | 375 × 812 | Controlled simulateError=true UI failure: visible error, retained lower form input, and restored controls. No POST or backend rejection occurs. |
| `reports/hw02/screenshots/part1/P1-06b-retained-upper.png` | 375 × 812 | Supplemental retained title, address, and email after the controlled UI error; original viewport remains 375 × 812. |
| `reports/hw02/screenshots/part2/P2-00-seeds.png` | 1100 × 1100 | Fresh isolated app instance contains original seed IDs 1 and 2. |
| `reports/hw02/screenshots/part2/P2-Q1-input.png` | 1100 × 1100 | Create input for Downtown San Jose Studio before submission. |
| `reports/hw02/screenshots/part2/P2-Q1-created.png` | 1100 × 1100 | Create returned home with newly assigned ID 3; its title, address, and remaining fields are displayed. |
| `reports/hw02/screenshots/part2/P2-Q2-before.png` | 1100 × 1100 | Before update: editor targets ID 1 with its original title and address prefilled. |
| `reports/hw02/screenshots/part2/P2-Q2-updated.png` | 1100 × 1100 | ID 1 now has Updated Downtown Apartment and 900 Market Street, San Jose, CA. Other fields and IDs 2 and 3 remain unchanged. |
| `reports/hw02/screenshots/part2/P2-Q3-before.png` | 1100 × 1100 | Before deletion: total 3, highest ID 3, and global Delete highest-ID listing (3) action. |
| `reports/hw02/screenshots/part2/P2-Q3-after.png` | 1100 × 1100 | The actual highest-ID DELETE returned 204; home now displays only IDs 1 and 2, total 2 and highest ID 2. |
| `reports/hw02/screenshots/part2/P2-Q4-title.png` | 1100 × 1100 | Title-only search Downtown returns ID 1. Downtown is absent from its address; the global store still contains two records. |
| `reports/hw02/screenshots/part2/P2-Q4-address.png` | 1100 × 1100 | Address-only search Market returns ID 1. Market is absent from its title; the global store still contains two records. |
| `reports/hw02/screenshots/part2/P2-Q4-clear.png` | 1100 × 1100 | Clear restores the two remaining records and an empty search query. |
| `reports/hw02/screenshots/part2/P2-Q4-no-match.png` | 1100 × 1100 | Supplemental no-match state retains the global two-record summary; this is distinct from Part 1’s truly empty store. |

Use raw PNGs with explicit report captions; there is no invented DevTools width toolbar. Mobile images can be set to about 2.4–2.7 inches wide for readability. Full square desktop screenshots should span report width, or be cropped in layout to their relevant existing UI region without changing pixels.

## Evidence files

- `capture-manifest.json`: timestamps, URLs, PNG dimensions/hashes, viewport measurements, input values, assertions, browser/console observations, source hashes.
- `network-events.json`: real browser request metadata/statuses; GET bodies and DELETE empty responses. Mutation body capture errors are explicit.
- `p1-*.json`, `p2-*.json`: actual read-only GET snapshots of each checkpoint, including before/after records.
- `server-console.txt`: timestamped actual Uvicorn startup/access/shutdown output. No startup-console image is claimed.
- `../../RUN_LOG_PART12.txt`: run chronology and limitations.

## Source SHA-256

- `code/web_application/main.py`: `72854596c956365df801bc86afb13e98b2eedefc1e910fc03b2cdf7aea824610`
- `code/web_application/static/index.html`: `f692b1133214d5da8e5a6e3e0bf35d454af287e7b4def2825cdce26b46f14efa`
- `code/web_application/static/styles.css`: `e318ec9f8e810b538390b957f35cb0ead807ba6c87846782776672de6f6eb403`
- `code/web_application/static/app.js`: `eda37f2102208b8ad74c3157699b7558c6b324d515f7648ad9915ed3173d04aa`

## Supplemental assignment-port proof

`reports/hw02/screenshots/part2/P2-00-port8702-readonly.png` (1100 × 1100) is an actual screenshot from the already-running app on port 8702 at 2026-09-14T07:19:56.212Z. All page requests were GET. Home and API returned 200; current seed IDs1 and2 were observed. It is a separate read-only observation, not part of the isolated CRUD sequence. Detailed URL, body, request list, viewport, and SHA-256: `port8702-readonly.json`. The original was visually inspected and readable.
