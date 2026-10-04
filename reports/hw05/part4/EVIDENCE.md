# Part 4 evidence - Pragya Apurva

Assignment items 22–24 / U6b. Code and offline verification are complete at
`c70bb92be1d0f2b0accfec51de462005e4aaf20a` on
`codex/hw5-part4-executor`, based on reviewed Part 2 commit
`158e946bb1e3ca647236fc72961e45da008c05f9`.

The required terminal screenshot remains pending because native terminal
capture tooling was unavailable in this chat. No image was synthesized or
substituted. The intended selected image path is
`reports/hw05/screenshots/part4/4-01-offline-tests-terminal.png`; it does not
exist yet. This part's required evidence is therefore incomplete even though
the code and offline tests pass.

## Selected evidence

Paths below are relative to `reports/hw05/raw/part4/`.

| File | Observed result and what it proves |
| --- | --- |
| `offline-run-1.txt`, `offline-run-2.txt` | Actual runner stdout: student name, six PASS lines, `6/6 passed`; byte-identical, both exit 0 |
| `canonical-cases.json` | Actual JSON strings, decoded envelopes, inputs and reader calls for all six cases; exact historical errors reproduced through the real service/executor |
| `pytest-focused.txt` | 83 passing executor/runner tests, no skips; includes guarded import/connection isolation, strict validation, serialization, subprocess failure status, and lifecycle doubles |
| `pytest-domain.txt` | 51 passing inherited pure domain-contract tests, no skips |
| `pip-check.txt` | `No broken requirements found.` in the isolated Python 3.12.13 environment |
| `intentional-failure.txt` | Expected negative control: one injected assertion fails, all six real cases still pass, `6/7 passed`, exit 1; never enabled in the normal runner |
| `optimized-rejected.txt` | Expected negative control: Python `-O` rejected with exit 2; no false passing assertion summary |
| `default-runtime-unavailable.txt` | Actual unmocked default call on this branch returns a JSON failure because Part 3's runtime is absent |
| `requirements-resolved.txt` | Exact installed package versions, preserving all unchanged direct requirement pins |
| `verification.json` | Exact commands, timestamps, exits, evidence/source SHA-256 hashes, Python/package versions, counts, screenshot status, and pending U6c status |

The source worktree was clean when these records were collected. Adding these
evidence files later does not change the tested application source. The source
hashes in `verification.json` identify the exact code and inherited contracts.
Records include both UTC and America/Los_Angeles execution times.

## Scope of the proof

All six required assertions use `RentalService(FixtureReader())` injected into
the real executor. There is no MySQL connection or LLM call. Subprocesses ran
with a minimal environment containing no DSN, live database/model
configuration, or API key. A focused guard test additionally blocks engine,
driver, socket and DNS calls, live-configuration access, and Part 3 runtime
imports, then checks that no guarded action was attempted.

The fixture deliberately excludes rental 8 and manager 4. Its public rows,
relationships, and expected count are fixed. The whitespace rejection reaches
no reader. The three rejection results were compared directly with the
historical Inspector `structuredContent` values in
`reports/hw05/raw/part2/rejected-cases.json`, without changing that evidence.
The current schema snapshot is the separate Part 2 `review-fixes` record.

Default factory and cleanup tests use isolated module doubles. They verify
per-call ownership and failure handling only. The selected default-call
transcript proves honest handling of an unavailable dependency, not a working
production path. No actual Part 3 retry behavior or upgraded MySQL reads were
verified here. Coordinator U6c remains pending after integration, including
all three default calls, real retry/cleanup behavior, strict inventory, and
comparison with MCP against the upgraded schema.

## Terminal image completion

Run the normal assertion runner in a real terminal using Python 3.12. Capture
the student's name, all six PASS/FAIL lines, and final `6/6 passed` together in
one readable frame. Preserve its actual output and record the capture time,
command, code revision, versions, and image hash. Inspect the actual image
before selecting it as submission evidence and updating `verification.json`.
Detailed machine-local capture steps are supplied separately to the user.

No Part 5 safety rule, agent loop, final report, tag, remote publication, or
other part's completion is claimed by this evidence.
