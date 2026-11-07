# Part 4 AI-use evidence

## 1. Assistance and supplied work

Pragya Apurva supplied the assignment, the Part 4 scope, the existing rental application and model adapter, and the required HW8 base. Codex authored the synthetic fixtures, agent implementation, regression tests, experiment runner, and evidence summaries, and executed the local checks and model runs.

## 2. One unsuitable output

The first AI-generated validation test combined two failing retention rules. Either failure could reject the lesson by itself, so a passing test could hide a broken rule.

## 3. How it was detected

The testing review bypassed each retention predicate independently in memory. The original test continued to pass. This showed that it checked the aggregate rejection without proving each rule was effective.

## 4. What changed

The test now isolates each retention rule with the other checks satisfied. It covers targeted first-answer degradation, a previously correct final answer becoming incorrect, an unrelated unsupported claim, and a lesson used outside its scope. Bypassing each predicate now makes the test fail. The final focused suite passed 42 checks, and all 40 held-out final answers were independently compared with the canonical facts while packaging the evidence.
