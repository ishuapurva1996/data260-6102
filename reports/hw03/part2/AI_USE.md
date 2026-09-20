# Part 2 — AI-use disclosure

## 1. What was the AI assistant used for, and what did the student do?

Codex and its collaborating agents prepared the Part 2 implementation, collected and cleaned the official source documents, drafted the five questions and expected answers from those documents, and audited the supporting source pages. The agents set up the local embedding environment, wrote and ran tests, executed the retrieval experiments, saved the raw data, reviewed all returned passages for answer support, regenerated metrics, prepared screenshots from actual saved output, and drafted the report material. The report's relevance judgments and source audits are attributed to agents in their saved evidence files.

The student supplied the assignment, personal writing preferences, execution instructions, and the requirement to keep Part 2 isolated from another session's Part 1 work. The available session evidence does not establish student-authored implementation, student-run experiments, or independent manual verification by the student. Any later student review or changes should be added truthfully during integration rather than inferred here. The local embedding model was used for retrieval; no LLM generated answers to the five graded questions and no paid inference API was used.

## 2. What AI-produced output was wrong or unsuitable, or what was independently verified?

An early AI-written verifier did not sufficiently bind the saved campaign's question text, expected source IDs and retrieval parameters to the committed input files. Checking the corpus hashes and recomputing numerical summaries was not enough: a saved record could describe a changed query or changed `k` while still containing mathematically consistent vectors and scores. This was an unsuitable gap in the evidence checks, even though the actual baseline used the frozen questions.

The check was performed by Codex agents reviewing the implementation and evidence independently of the initial code-writing step. It is not a claim that the student independently verified the code.

## 3. How was the problem detected or the result verified?

The agent review compared the verifier with the experiment's requirement that results come from committed, unchanged questions and configuration. Targeted negative tests then changed a saved question, its expected source IDs, the requested `k`, or the run configuration. These changes must be rejected even when the surrounding artifact structure remains valid. The regression test `test_campaign_must_match_frozen_query_gold_config` in `tests/retrieval/test_verification.py` exercises those mismatches.

Additional verification checks the frozen corpus and code hashes, all 15 question/method combinations, saved vector shapes and cosine calculations, indexed and retrieved text, annotation coverage, and offline regeneration of the summary. The relevance review read the complete returned text rather than accepting a source match or high score as proof. Its Q2 example demonstrates why this matters: the token result scored 0.7510996281013915 but omitted the required $480 answer. These checks provide recorded evidence; the five-question experiment does not establish general retrieval accuracy.

## 4. What changed, and why does it work now?

The verifier now calls `validate_campaign_contract` to compare the run's full question list and configuration with the frozen inputs. It also checks each result record's question text, designation, expected sources, requested `k`, measured-search count and warm-up count. The negative tests ensure that altered values raise an error, closing the specific gap between the committed experimental design and the saved result records.

The baseline remains tied to input-freeze commit `08bd6e0495ce03281aa8fab7f70ac0b51e1c1442` and tested retrieval-code commit `cc0a57bae6e19778021643bffebf5c66d5e7c0a3`; subsequent verification and report work does not rewrite the measured run. Final checks and their commands are recorded in `reports/hw03/part2/verification.json` and `reports/hw03/part2/RUN_LOG.txt`. This disclosure covers Part 2 only and makes no claim about the student's later review, Part 1, final report assembly, publishing or submission.
