# Part 4 branch results

Pragya Apurva, SID4 6102. Tested code: `761d48c`.
This is standalone file-mode evidence for integration, not the final report.

| Item | Observed result |
| --- | --- |
| Original committed before consolidation | `8423cbd`; 55 physical lines, 54 counted lines/entries |
| Final runtime and selected snapshot | 28 physical lines, 27 counted lines/entries |
| Duplicate groups | Three ten-entry groups merged, retaining every source ID |
| Contradictions | Budget F01/F02 -> F02 current; date F03/F04 -> F04 current; parking F05/F06 explicitly unresolved |
| Independent final audit | All 54 original source IDs and values preserved; zero incorrectly resolved contradictions |
| Offline checks | 61 passed: 22 Part 4 cases and 39 shared/HW1 regression cases; three existing dependency deprecation warnings |
| Live commands | `/help`, `/memory`, `/compact`, `/dream` all demonstrated with local qwen2.5:7b through HW1 adapter and A's lease |
| Process restart | File bytes and consolidation timestamp unchanged; corrected budget/date and ambiguous parking recalled appropriately |
| Dream/restart | One user-grounded stove fact appended to an isolated file; user quote persisted; fresh process recalled induction stove |
| Common comparison scenario, file side | After correction/restart: 2400 USD current, 2200 USD superseded, Willow Glen, one cat |

The first local-model run invented a parking correction and was rejected before
writing. The second run consolidated correctly but misread a persisted stove
requirement after restart. Raw outputs remain in attempt-01 and attempt-02.
The final code makes correction arrays explicit and persists the verbatim user
quote/source-message ID. Attempt-03 and the file-side common scenario passed.
Zero incorrect final resolutions does not mean there were no bad model outputs.

The live generation configuration was qwen2.5:7b, temperature 0, context 4096,
output limit 512, seed 6102, timeout 180 seconds. Its installed digest is recorded
in attempt-03/provenance.json. The largest reported prompt in that final exercise
was 1364 tokens. These are demonstration observations, not Part 3 measurements.

See VERIFICATION.json, SOURCE_SNIPPETS.md, INSTRUCTION_VERIFICATION.md and
AI_USE_FACTS.md for machine-readable checks and report-ready source/evidence
locations. FILE_MODE.md contains interface details, counting rules, file-mode
limits and exact comparison commands.

A still needs to integrate these commits, run the common scenario against both
systems, capture real terminal/application screenshots with Pragya Apurva visible,
and complete final acceptance/report packaging. No observed MongoDB comparison,
scalability benchmark, push, tag or submission is claimed.
