# Part 3 probe scoring

The five questions, criteria, source-turn quotations and 1-5 rubric were frozen before measurement in root `memory_probes.yaml`. Codex Session D assessed the actual answers criterion by criterion, without a judge-model API. No question, expected fact or threshold was changed after observing responses.

A missing essential detail scores at most 3; an incorrect essential assertion scores at most 2 and disqualifies a setting. Score 5 requires all criteria. A correct indoor-cat answer omitting Juniper scores 4. The date question has no score-4 minor omission. For accessibility, a generic step-free route without its endpoint does not establish the required continuous route into the unit. A route explicitly spanning the building entrance to the unit meets that criterion. Requiring a working elevator for above-ground units also excludes stairs-only access.

| Condition | Probe | Score | Explanation |
|---|---|---:|---|
| A | budget | 5 | Both the current amount and the superseded amount are explicit and correct. |
| A | neighborhood | 5 | Recalls the exact neighborhood and city without a contradictory target. |
| A | pet | 4 | The accommodation for one indoor cat is correct; omitting Juniper is the frozen score-4 minor omission. |
| A | move_in | 5 | The exact full move-in date matches the script. |
| A | accessibility | 3 | Correctly recalls the conditional working elevator and mentions step-free access, but omits the essential continuous route into the unit and its entrance origin. This is an important omission, so score 3 rather than the score-4 minor omission. |
| B | budget | 5 | Both the current amount and the superseded amount are explicit and correct. |
| B | neighborhood | 5 | Recalls the exact neighborhood and city without a contradictory target. |
| B | pet | 4 | The accommodation for one indoor cat is correct; omitting Juniper is the frozen score-4 minor omission. |
| B | move_in | 5 | The exact full move-in date matches the script. |
| B | accessibility | 3 | The step-free route and conditional working elevator are recalled, but the required continuous route into the unit is not specified and the entrance origin is absent. Treat the missing essential endpoint consistently with A: important omission, score 3. |
| C | budget | 5 | Both the current amount and the superseded amount are explicit and correct. |
| C | neighborhood | 5 | Recalls the exact neighborhood and city without a contradictory target. |
| C | pet | 4 | The accommodation for one indoor cat is correct; omitting Juniper is the frozen score-4 minor omission. |
| C | move_in | 5 | The exact full move-in date matches the script. |
| C | accessibility | 5 | Recalls the continuous entrance-to-unit route and conditional working-elevator requirement, with no contradictory addition. |
| D | budget | 5 | Both the current amount and the superseded amount are explicit and correct. |
| D | neighborhood | 5 | Recalls the exact neighborhood and city without a contradictory target. |
| D | pet | 4 | The accommodation for one indoor cat is correct; omitting Juniper is the frozen score-4 minor omission. |
| D | move_in | 5 | The exact full move-in date matches the script. |
| D | accessibility | 5 | Recalls the continuous entrance-to-unit route and conditional working-elevator requirement, with no contradictory addition. |

Exact unedited answers, answer SHA256, request IDs, frozen criteria, individual correct/missing/incorrect assessments, explanations, scorer and scoring timestamps are in `../raw/part3/scores.json`. No scoring item is pending. The frozen selection rule treats missing and incorrect facts separately; A and B still meet the declared aggregate threshold despite their accessibility omissions.
