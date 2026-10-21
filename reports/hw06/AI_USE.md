# AI use in Homework 6

1. **What I used AI for and what I did myself.** I used AI to break the assignment into smaller parts, compare approaches, debug edge cases, explain syntax, and test boundaries. It also helped write and test parts of the code, check measurements, and draft the report. I reviewed the results against the assignment.

2. **An AI answer that was wrong.** During file-memory consolidation, the model decided that parking was no longer needed. My notes contained both "parking required" and "parking unnecessary," but neither statement corrected the other. The model chose one without evidence.

3. **How I found the problem.** I checked the original memory entries and the saved result. The code rejected the model's parking decision, so both statements stayed in the file. I also checked that the shorter file still contained all 54 original fact IDs.

4. **What I changed.** I made the model check the written correction links before choosing which fact is current. The code now rejects a choice without such a link. It kept the corrected budget and move-in date, while leaving the parking question unresolved.
