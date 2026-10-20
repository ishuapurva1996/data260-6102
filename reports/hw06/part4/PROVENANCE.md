# Part 4 original fixture provenance

Pragya Apurva, DATA 260, SID4 6102. Synthetic rental preferences, not personal data.
Foundation: `51cfd410400683acf7cf9f7bb88a9581ba3834bb`.

The first Part 4 commit contains the original runtime MEMORY.md and byte-identical
raw/part4/MEMORY.original.md, fixture generator, predeclared expected_conflicts.json,
expanded HW1 AGENT.md, service, CLI and offline tests. It precedes consolidation.
The original has one UTC metadata comment and 54 facts: exactly 55 physical lines.
Three groups each contain ten duplicates. The three contradictory pairs are budget
F01/F02, move_in F03/F04, and parking F05/F06. Explicit correction references select
F02 and F04; parking is deliberately unresolved. All claims must survive the run.
The expected result is 27 entries plus one metadata line, or 28 physical lines.

Fixture setup is explicit: scripts.hw06.part4.fixture.write_original(root).
Importing it does not write files; the normal CLI never resets memory.
Do not run fixture setup on a user's existing memory.

Verification before original commit: 20 offline tests passed. The initial test run
failed collection because the service did not yet exist. The first implemented run
passed 15 tests and exposed one incorrect physical-line expectation in the test
fixture (seven instead of six); the assertion was corrected by counting the actual
input lines. These observations are engineering checks, not live-model results.

AI-use facts: Codex authored the Part 4 code, synthetic fixture and tests from the
assignment and shared contract. The human supplied the scope, requirements and
ownership boundaries. Behavioral tests and the separate post-run conflict audit
check outcomes; no claim of human execution or review is made. Live model identity,
raw outputs, failures and actual source revision will be recorded with the run.
