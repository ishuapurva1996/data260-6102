# Part 4 follow-up diagnosis

This note records the completed local development experiments reviewed on September 28, 2026. Later sections preserve the successive checkpoints: initial 3B diagnosis, unsuccessful 7B answer-generation trials, retrieval experiments, and a passing integrated pilot using separate models for question interpretation and final answers. All earlier scored runs and development outputs remain evidence, including failures. This note does not change their judgments.

The follow-up has two distinct goals: produce complete answers with correct source citations when evidence supports them, and ask for clarification when the question leaves the needed subject or process unspecified. The first successful, supported, cited C answer is **our reviewed plan's completion criterion**, not an explicit minimum stated by the assignment. Exact Q5/Q6 refusal behavior, the complete experiment matrix, evidence collection, and reporting are evaluated separately.

## What failed in the saved run

In [scored-20260928-03 responses](../raw/part4/scored-20260928-03/responses.jsonl), `Q3-C-k3` receives three passages. Its third passage contains both required facts: disclose known information about lead-based paint or hazards, and provide available records and reports. All three candidates survive filtering. The model nevertheless returns exactly `[1]`.

This is present in the raw Ollama response as well as the saved answer. The response reports `done=true`, `done_reason=stop`, `eval_count=4`, and `prompt_eval_count=704`. The answer reserve is 768 tokens within a 4,096-token window. There is no transport error, output-limit stop, postprocessing removal, or context overflow explaining the missing prose. The runtime assigns the raw `response` string directly to `answer`.

The independent development analogue is D4: “According to the EPA disclosure article, how long should signed disclosures be kept?” Its one retained chunk says, “Keep a signed copy of the disclosures for three years after the sale is completed or the lease begins.” That complete fact is already inside the actual context; it was not supplied from an answer key.

The [baseline reproduction](../raw/part4/development-followup-baseline-01/responses.jsonl) returns exactly `[1]` for D4, with four generated tokens, normal `stop`, and 317 prompt tokens. D2 also returns `[1]`, although D2 additionally lacks its requested fact in the retrieved context. D1 produces correct cited prose using the same model, API, and settings. Thus the interface can return prose, and a lone citation is a real model failure rather than evidence of an unusable transport or template.

## Development criteria and controlled change

The [acceptance criteria](../raw/part4/followup-setup-20260928/development_acceptance_predeclared.json) were fixed after the baseline reproduction and before the first changed-prompt probe. All eight existing development questions remain in each probe. The candidates, retained text, local 3B model, temperature 0, seed 6102, 4,096-token window, and 768-token answer limit remain fixed for the direct prompt comparisons. No scored question, question ID, gold passage, or expected answer selects a runtime response.

| Development question | Required context-appropriate behavior |
|---|---|
| D1 | State cold water and that boiling does not remove lead, with citations that actually support both statements. |
| D2 | Refuse exactly because the supplied passages do not give the HUD complaint deadline. The two-year private-lawsuit deadline is a different process. |
| D3 | Refuse exactly because the supplied passages do not give the dependent-deduction amount. |
| D4 | State three years and the sale-completion or lease-commencement trigger, with a supporting citation. |
| D5, D6, D8 | Use exactly `I cannot answer this question from the provided documents`, ignoring only outer whitespace when checking equality. |
| D7 | Ask which case or process is meant, without choosing a deadline or inventing a case. |

D2/D3 are answerable from the full corpus but not from their actual retained context. Appropriate refusal passes this generation-behavior gate while their retrieval and full-corpus answer accuracy remain failures. This distinction prevents safe abstention from inflating answer accuracy. If a general retrieval change later supplies their full evidence, their required behavior becomes a complete, correctly cited answer.

The smallest useful prompt change replaces the final “Be concise” instruction with an explicit prose contract: write the answer in complete sentences, place supporting evidence numbers after factual statements, do not return a citation alone, and cover every part of the question. The [answer-body probe](../raw/part4/development-followup-body-01/responses.jsonl) changes D4 to this unedited model output:

> According to the EPA disclosure article, signed disclosures should be kept for three years after the sale is completed or the lease begins. [1]

D4 now uses 29 generated tokens and stops normally. D1 remains correct and cited. D2 now refuses instead of returning `[1]`; D3 and the three unsupported questions also refuse exactly. D7 still refuses instead of clarifying. The result is **7/8 context-appropriate behaviors**, including both required development answer demonstrations, but it fails the full development gate.

## All completed 3B follow-up probes

These counts are assistant semantic judgments against the criteria above, not an automated proof of answer correctness. Each linked directory preserves the exact requests, responses, probe source, metadata, and hashes.

| Probe | Main change | Gate result | Observed failure |
|---|---|---:|---|
| [baseline](../raw/part4/development-followup-baseline-01/) | Reproduce original prompt | 5/8 | D2/D4 citation only; D7 refuses. |
| [body](../raw/part4/development-followup-body-01/) | Require complete answer prose and citations | 7/8 | D7 refuses. |
| [decision](../raw/part4/development-followup-decision-01/) | Ordered clarify/decline/answer response modes | 4/8 | D1/D4 omit citations; D2 incorrectly assigns two-year lawsuit rule to HUD complaint; D7 refuses. |
| [clarify](../raw/part4/development-followup-clarify-01/) | Explicitly allow clarification without evidence or citations | 7/8 | D7 refuses. |
| [example](../raw/part4/development-followup-example-01/) | Neutral “Is it ready?” clarification example | 7/8 | D7 refuses. |
| [system](../raw/part4/development-followup-system-01/) | Put clarification-first instruction in system role | 7/8 | D7 refuses. |
| [analogy](../raw/part4/development-followup-analogy-01/) | Explain multiple possible processes; unrelated processing-fee example | 7/8 | D7 refuses. |
| [scope](../raw/part4/development-followup-scope-01/) | Open with help through clarification or evidence-based answer | 6/8 | D7 refuses; D6 adds a period, failing the exact refusal rule. |
| [routing](../raw/part4/development-followup-routing-01/) | Separate question-only specificity classification before generation | 5/8 | D3/D8 are unnecessarily clarified; D7 still refuses. |
| [rules-last](../raw/part4/development-followup-rules-last-01/) | Put question and evidence before the response instructions | 4/8 | D4 refuses despite sufficient evidence; D2/D6 add periods to refusals; D7 still refuses. |

These ten runs preserve 80 final development outputs. The routing run also preserves eight auxiliary model calls. All 80 final responses stop normally. The request text and changing prompt-token counts confirm that altered prompts reached the model. For example, D7's prompt counts are 281 for baseline, 315 for body, 364 for clarify, 394 for example, and 396 for analogy. Repeated identical answers therefore do not mean that the new instructions were never submitted.

The question-only routing experiment is particularly informative. Its classifier receives no retrieved excerpts and is asked to distinguish specificity from knowledge of the answer. It labels D3 `CLARIFY` even though the named handbook and requested deduction are sufficient for a targeted lookup; it labels D8 `CLARIFY` despite the specified profession, city, and date; and it labels D7 `CLEAR` even though “my case” leaves the process unspecified. The final D3 output asks who or what the handbook is for; D8 asks what data source the user would use; D7 retains the exact refusal. Those outputs are not accepted as appropriate clarification.

## Interpretation and limits

The answer-body comparison supports a narrow conclusion: making the prose requirement explicit remedies the D4 citation-only failure under this fixed development context. It does not establish that every question or model benefits, nor that the improved prompt will repair Q3 before a fresh scored run. The failed decision rewrite shows that a longer or more structured prompt can also lose citations and introduce incorrect facts.

The clarification probes reveal a persistent failure to distinguish an unspecified question from unavailable evidence. Retrieved lawsuit text might anchor the single-stage answer, but it cannot be the sole explanation: D7 is misclassified even in the evidence-free routing call. The evidence supports an instruction-following or semantic-discrimination limitation under these tested settings. It does not prove the model's internal cause. There is no basis here to weaken D7's expected behavior, reinterpret its refusal as clarification, or accept added punctuation in an exact refusal.

The experiments use only eight repeatedly inspected development questions and deterministic single calls. They are calibration evidence, not an independent estimate of general reliability. New scored outputs must remain untouched even if the chosen development configuration later fails.

## Q1 and Q2 retrieval diagnosis

The [saved retrieval records](../raw/part4/scored-20260928-03/retrievals.jsonl) locate failures before generation. Q1's three candidates discuss reconsidering denied applicants, application-record retention, and HUD referral to a local agency, with similarity scores approximately 0.667, 0.605, and 0.601. None contains the requested 14-day meeting rule, although that rule exists in a single actual chunk. All scores exceed C's 0.50 relevance cutoff. A threshold cannot recover a relevant passage that never enters the candidate set.

For Q2, the highest-ranked passage correctly explains risk assessment, with score 0.825. The standalone paint-inspection definition is absent at every saved k of 1, 3, and 5. At k=3, the extra candidates discuss a buyer's inspection opportunity and a combined inspection/risk-assessment procedure. At k=5, the added passages concern disclosure paperwork and records. These are related to lead paint but do not supply the missing standalone definition. All survive the existing cutoff; neither a budget drop nor deduplication causes this miss.

The [preflight semantic review](preflight_review.json) identifies the sufficient Q2 pair, `EPA_LEAD:3830114fcc78:0008845-0009262` and `EPA_LEAD:3830114fcc78:0009535-0009993`, and explains why the combined-procedure passage cannot answer the complete question by itself. That audit is evaluation evidence only. It must not be used to inject the missing chunk into generation. The observed failure is consistent with semantic similarity favoring topical passages over complete fact coverage, especially for a question with two requested concepts. The saved top-k records do not establish the missing passage's full-index rank or prove that a particular retrieval redesign would fix it.

## Checkpoint before the larger-model probe

The 3B answer-body improvement is worth retaining for testing, but no completed 3B variant passes the eight-question gate. Further blind wording changes are paused. One bounded attempt with the public local Qwen2.5 7B model is pending; it must demonstrate both supported cited development answers, appropriate D7 clarification, and exact D5/D6/D8 refusals before any new scored call. This larger model is a new experimental variable and must be recorded as such.

If a development configuration passes, freeze the model identity, tokenizer, prompt, retrieval/filtering settings, source/code hashes, and gate evidence. Then generate the entire 22-answer matrix using that frozen configuration, retain all failures, and refresh semantic judgments, tables, genuine screenshots, the report analysis, verification, and handoff. Automated checks can establish artifact completeness, hashes, citations' valid identifiers, exact strings, and output provenance. Assistant review must still assess whether the answers are complete, the cited passages support each claim, and the clarification is appropriate. Neither kind of verification substitutes for the other.

## First 7B development result

The [7B answer-body probe](../raw/part4/development-followup-7b-body-01/responses.jsonl) subsequently completed all eight calls with normal stops. It reuses the saved development contexts and answer-body prompt, changing the local model and matching tokenizer. Independent assistant review records **6/8**, with exact evidence quotes and the response-file hash in [gate_assessment.json](../raw/part4/development-followup-7b-body-01/gate_assessment.json).

D1 and D4 are complete and correctly cited. D3, D5, D6, and D8 refuse exactly. D2 instead answers about private lawsuits even though the question asks when to file a complaint with HUD and the actual context lacks that deadline. D7 states, “The deadline for filing a lawsuit is 2 years from the time during which HUD was not processing your complaint [1].” This selects a process the user did not specify and misstates the cited passage's exclusion of HUD processing time. It is not clarification. A larger model therefore does not repair the gate by itself. This configuration remains ineligible for a scored rerun; further work must preserve the same acceptance criteria.

## Further 7B and retrieval trials

Three additional completed 7B generation probes retain the same eight development questions and their saved contexts. The [analogy probe](../raw/part4/development-followup-7b-analogy-01/) passes 4/8: it still answers the wrong process for D2, adds periods to D3/D5 refusals, and selects a lawsuit deadline for D7. The [question-only routing probe](../raw/part4/development-followup-7b-routing-01/) passes 7/8. Its separate 7B classifier correctly returns `CLEAR` for D1–D6/D8 and `CLARIFY` for D7, whose final output is, “Could you provide more details about the type of case you are referring to?” D2 remains an unsupported answer to the wrong process. The [exact-support prompt variant](../raw/part4/development-followup-7b-exact-01/) preserves correct routing but passes only 6/8: D2 remains wrong and D5 adds a period. Neither the correct routing nor plausible related prose excuses those failures.

A [hybrid retrieval inspection](../raw/part4/development-followup-hybrid-inspect-01/) combines dense retrieval and lexical ranks through reciprocal-rank fusion. It retrieves the dependent-deduction amount for D3, but D2's top three still lack the HUD complaint deadline. A subsequent [local reranker inspection](../raw/part4/development-followup-reranker-inspect-01/) scores the top 20 hybrid candidates with `cross-encoder/ms-marco-MiniLM-L6-v2`, pinned to revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`. D3's supporting chunk becomes rank 1. D2 still receives the 30-day agency-referral passage, private-lawsuit deadline, and reconsideration passage as its top three. These two inspections generate retrieval evidence, not final answers; no scored question or gold passage selects the runtime candidates. The reranker is rejected, and the integrated pilot returns to the unchanged dense retrieval configuration. The saved model assets and failed retrieval comparisons remain available.

## Integrated development gate

The development observations suggest different model roles: the 3B answer-body prompt produces supported cited prose and safe abstention in 7/8 cases, while the 7B question-only classifier makes all eight interpretation decisions correctly. The [integrated pilot](../raw/part4/development-followup-integrated-01/) therefore uses 7B only for that auxiliary decision and 3B for every final answer. This is a general role separation. It does not choose a model by question ID, expected answer, source location, or observed scored response.

The integrated run rebuilds and queries the real unchanged dense index. Each C request first sends only the question and generic specificity instructions to 7B. A `CLEAR` decision invokes the 3B answer-body prompt with the filtered retrieved context. A `CLARIFY` decision invokes 3B with a generic request to ask about the missing subject/process and no retrieved context. The clarifying question is generated; it is not a fixed answer string. Exact requests, all eight routing results, all eight final outputs, retrievals, timings, model identities, and frozen inputs are preserved. The run completes with `status=recorded`, normal final stops, and no recorded live-input changes.

Independent assistant semantic review gives **8/8 context-appropriate behaviors**, with both required supported cited development answers. D1 states cold water and the boiling limitation with actual supporting citations. D4 states three years and the sale/lease trigger with its supporting citation. D2/D3 appropriately refuse their incomplete retrieved contexts; these remain retrieval and full-corpus answer failures. D5/D6/D8 refuse exactly. D7's unedited final output is:

> What is the process or document I need to check to find the deadline for my case?

The first-person wording is awkward. Nevertheless, it asks the user to identify the missing process or document instead of selecting a case type or deadline. This satisfies the unchanged clarification criterion. It makes no factual claim and requires no evidence citation. This interpretation is explicitly recorded rather than hidden behind a punctuation or keyword test.

The [integrated gate assessment](../raw/part4/development-followup-integrated-01/gate_assessment.json) contains each exact answer, semantic reason, supporting citation/quote checks, response hashes, model roles, and limitations. At this checkpoint the fifteen generation probes preserve **120 final development outputs and 32 auxiliary routing calls**, including every failed variant. The gate permits freezing this integrated configuration before a complete scored rerun; it does not predict that the scored answers will all succeed. No scored answer has been substituted, manually repaired, or credited using a development result.

## Frozen scored follow-up result

After the passing assessment at 05:47:48 UTC, configuration freeze occurred at 05:48:33 UTC. The complete [scored04 run](../raw/part4/scored-20260928-04/) then recorded 22 final answers and 8 auxiliary decisions, all normal stops. Fresh assistant semantic review gives A 2/6, B 3/6, C 4/6 accuracy. Q3-C supplies both obligations with supporting [1], [3] citations; Q4-C asks which process and jurisdiction; Q5/Q6-C retain exact refusals. Q1/Q2 failures remain, and no tested sweep k gives a complete supported cited Q2 answer. These outcomes support the narrow requested repair, not general reliability. The [verification receipt](verification.json) distinguishes 12 automated evidence checks from 1 plan criterion based on saved semantic judgments.
