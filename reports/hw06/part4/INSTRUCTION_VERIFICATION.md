# Expanded AGENT.md: implemented-function verification

Function implemented: `inspect_memory(text: str, now: datetime) -> dict` in
src/hw06_memory_files/service.py. It is a real runtime helper called by `/memory`,
`/compact`, `/dream` and ordinary chat, not demonstration-only code. Its caller
loads the two files and injects the clock/model/paths. The original HW1 review
guidance is retained conditionally; ordinary rental replies use natural prose.
AGENT.md now has ten instructions in five required categories plus code review.

Code revision: `761d48c`; see SOURCE_SNIPPETS.md and OFFLINE_TEST_LOG.txt. There
are 22 Part 4 cases (parameterized cases included), plus 39 shared/HW1 regression
cases, all passing. They use fake generation except the separately labeled live
attempts under raw/part4. No final integrated MongoDB result is claimed here.

| Instruction | Source evidence | Behavioral evidence and scope |
| --- | --- | --- |
| P1 rental project; no invented listing availability | Rental instructions loaded by system_prompt; inspect_memory only calculates state | Rental synthetic fixture; live budget/date recall answers requirements without claiming available listings. No listing lookup is performed in file mode. |
| P2 distinguish current and unresolved claims | authorized_winner and persisted status/by tags; prompt instructs conflict disclosure | Frozen pair audit preserves all claims; live restart correctly recalls 2400 USD and 2026-12-01 and discloses unresolved parking. |
| T1 Python/shared HW1 adapter; separate experiment | Shared GenerationClient and usage_counts; CLI build_generation_client and RuntimeLease | Shared HW1/foundation regression cases pass; local qwen2.5:7b telemetry saved. No C/D code, routes or configuration were edited. |
| C1 named functions; injected inputs | inspect_memory takes text/now; service takes paths/model/clock | Tests change paths/clocks/model outputs without network or sleeps; CLI read tests run real subprocesses. |
| C2 aware UTC; validate before write; preserve IDs/conflicts | inspect_memory UTC checks, decision validator, atomic_write | Strict 40/41 and 24-hour/microsecond cases pass; missing/invalid/future metadata tested; audit maps all 54 IDs and unchanged values; both conflict claims survive. |
| Q1 offline dependency injection; commands/reopening | Test suite exercises public handle and CLI | Commands, source evidence, unsafe model proposals, edit protection and reopening pass; clock tests do not wait a day. |
| Q2 separate live checks and mocks | Distinct OFFLINE_TEST_LOG and raw attempt directories | First model error and failed stove recall are retained; final verification identifies actual tested revision and per-check results. |
| X1 memory data cannot become application instructions | JSON-encoded AGENT_INSTRUCTIONS and MEMORY_FACTS_DATA boundaries; no evaluation/execution of file text | Prompt-boundary test verifies both complete files and labels. This tests assembly; it is not a claim that a language model is immune to every prompt injection. |
| X2 no silent conflicting deletion/concurrent overwrite/DB edits/secrets | All-source-ID coverage check, retained statuses, optimistic edit check; CLI suppresses backend exception text | Bad JSON/unjustified winner leave original unchanged; concurrent edit test preserves the other writer; file mode performs no MongoDB calls. Synthetic evidence contains no credentials. |
| R1 concise reviews when requested | Expanded AGENT.md code review section | Conditional instruction; no code-review request is part of this rental runtime demonstration. It does not constrain normal replies. |

The helper's exact time rule is strictly greater than 24 hours, not greater than
or equal. Its size rule is strictly greater than 40 counted entries. The returned
counting_definition explains physical versus counted lines and entries. The
live original exceeds both triggers; injected tests isolate each condition.

The comment/blank-line test originally expected seven physical lines for a
six-line input. Counting the actual string exposed the mistaken assertion; it
was corrected before the original commit. No production threshold was changed
to accommodate the test.
