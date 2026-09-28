# Part 1 review and fixes

The implementation used the local `ce-work` workflow and separate simplify/review passes. Code reuse, code quality, and efficiency checks found no worthwhile behavior-preserving simplification. A full local review collected seven reviewer passes and independently validated six P2 findings. The final required report worker could neither start nor resume because the host reached its agent thread limit. No completed `ce-code-review` receipt is claimed.

Code review: skipped (ce-code-review unavailable) — the final dedicated receipt was unavailable after the terminal agent-limit failure. The underlying local reviews and validator results are retained under `raw/part1/review/`. The caller then performed the explicit final manual diff scan required by the workflow fallback and applied all six validated findings. An optional external peer attempt was rejected by automatic approval review; no source was transmitted, and the local adversarial pass supplied the alternative review.

Fix-worker launch and resume attempts also hit the same limit, so the parent applied the bounded fixes inline. No reviewer or fix worker committed changes.

| Finding | Resolution | Verification |
| --- | --- | --- |
| #1 Old-session 401 clears a new login | API requests capture a UI session generation; login/logout advance it, and a late old response cannot expire the current generation. No token is stored in this counter. | Delayed old-session 401 after fresh login browser case passes. |
| #2 Cancel remains active during a pending write | Cancel becomes disabled explanatory text until the write settles. | Actual regression first failed with one active Cancel link, then passed with no active link. |
| #3 Home becomes stale after leaving a pending write | Successful rental callbacks publish `rentals-changed`; a mounted Home refetches independently of the original form's lifetime. | Delayed create completes after navigating Home; new listing appears without a manual reload. |
| #4 Missing client-validation and failed-load tests | Added invalid primary fields/email/description/terms cases, valid 26-character boundary, and auth/list failure retry checks. | Expanded mock suite passes 19/19. |
| #5 Expiry runner requires preexisting rental | Expiry waits for loaded Home (`.result-count`), which also exists for an empty list; it no longer requires an article. | The shared loaded-Home helper passes the mock empty-state case and real expiry checks. No existing database rows were deleted to manufacture an empty fixture. |
| #6 SIGTERM skips owned-runtime cleanup | SIGTERM/SIGINT raise a controlled exit through `finally`; browser/server groups receive bounded termination with a kill fallback. | Actual SIGTERM check returns143, writes status interrupted, records every server stopped, and verifies8702 is free. |

Final manual scan covered source scope, six/two-field payloads, cookie handling, route guards, stale response/event cleanup, pending navigation, server ownership, output redaction, source fingerprints, output-directory options, and evidence claims. Browser capture waits for the list to finish loading and bounds full-page capture height for the later 5,000-row integration dataset. There are no unresolved accepted correctness findings. The documented Router6 npm advisories remain a dependency limitation under the shared version contract.

No standalone frontend lint or typecheck command exists. Relevant verification uses the production build, browser assertions, syntax checks, and whitespace checks; no unrun lint/typecheck result is claimed.
