# Baseline answer-support review

The annotations in `../raw/part2/baseline-20260920/annotations.json` are **Codex agent judgments**, not a claim that the student manually reviewed the results. The review read the five committed questions and expected answers in `../questions.yaml`, then every complete `retrieved_text` and `context_text` for all 45 saved hits in `../raw/part2/baseline-20260920/records.json`. Identical central/context texts were checked as identical rather than treated as separate evidence. No retrieval or embedding calls were made during this review; no saved raw result was modified.

The reviewed records have SHA-256 `8bd0a5ab188739e61afed8fd7dac6a48e61494ba86ccf01984b70d56ccff8564`.

## Decision rule

A positive label requires the **individual text** to provide every fact requested by the question. Labels do not rely on the document ID, preview, similarity score, or another retrieved hit. Central and expanded-context support are separate. Each annotation contains exact quotations from its actual saved text plus a rationale explaining the supported facts or the missing facts. All 90 central/context quotation fields were checked as exact substrings of their corresponding saved texts.

For Q1, the requested deadline is 14 days to request a meeting, not 5 business days for the owner's later decision. Q2 requires the frozen handbook's $480 per eligible dependent; general rent-calculation language does not suffice. Q3 requires both the boiling fact and the cold-water instruction. Q4 requires one year to file a complaint with HUD, not the two-year private-lawsuit deadline or investigation deadlines. Q5 requires the minimum 40% of assisted units that become available during the project fiscal year, not a minimum tenant payment or a minimum applicant income.

## Label totals

| Technique | Hits reviewed | Full central support | Full context support | Questions with central support in top 3 | Questions with context support in top 3 |
|---|---:|---:|---:|---:|---:|
| Token | 15 | 1 | 1 | 1/5 | 1/5 |
| Semantic | 15 | 2 | 2 | 2/5 | 2/5 |
| Sentence window | 15 | 3 | 5 | 3/5 | 4/5 |
| Total | 45 | 6 | 8 | — | — |

The positive token hit is Q3 rank 1. The positive semantic hits are Q1 rank 2 and Q3 rank 1. The positive sentence-window central hits are Q1, Q4 and Q5 rank 1. Sentence-window Q3 ranks 1 and 2 become positive only after context expansion.

For Q3, sentence-window rank 1 is “Boiling water does not remove lead from water.” Rank 2 gives the cold-water instruction. Each central sentence alone is partial support, even though the two hits together could answer the question. Each expanded window independently includes both facts, so both context labels are positive. This distinction directly shows what context expansion contributes.

## Highest-scoring rank-1 failure

After the support decisions, rank-1 scores were inspected using the declared high-score threshold of cosine >= 0.50. The strongest scored rank-1 result that failed both support tests was **Q2, token, rank 1**, node `token:f58b648d83a6c2ff:000000`, with cosine **0.7510996281013915**.

The question asks how much is deducted from annual income for each eligible dependent. The retrieved passage says:

> The amount of assistance paid on behalf of the family is calculated using the family’s annual income less allowable deductions.

The complete text is an introductory discussion of income, rent and deductions. It never gives $480, identifies the dependent deduction, or supplies any other amount per dependent. Its context is identical to its central text. The high cosine is consistent with shared subject matter and terms such as “annual income,” “deductions,” “family” and “rent,” but it does not demonstrate answer support. That explanation is an interpretation of the observed text overlap, not a measured attribution of the embedding model's internal behavior. The hit comes from the expected document yet fails the answer-support test, illustrating why source-match accuracy and cosine similarity cannot substitute for inspecting the returned text.

A second clear failure is **Q4, token, rank 1**, cosine **0.7208612331309348**, node `token:e8dcdb0274d129da:000021`. It says “You must file your lawsuit within two (2) years of the most recent date of alleged discriminatory action.” The question concerns a complaint filed with HUD, for which the expected text says one year. The retrieved text discusses a different process with a different deadline. Both central and context labels are false despite matching the expected source and subject area.

## Borderline judgment and sensitivity

**Q5, semantic, rank 2**, node `semantic:d1f9239a9a35969b:000049`, is the main judgment call. Its example says:

> Admit extremely low-income families to the first 40% of expected vacancies and then admit eligible applicants from the top of the list regardless of income.

The complete passage includes a Section 8 example, an annual turnover estimate, a selected admissions policy and a progress log. It offers useful partial support for the 40% figure. It does not explicitly state the general minimum obligation for assisted units actually becoming available in any project fiscal year; the example's expected-vacancy policy and rounding are not the full requested rule. Under the strict complete-answer criterion, both labels remain false. A second Codex agent independently read this hit and agreed that the strict label is defensible while requesting that its sensitivity be disclosed.

If the example were accepted as sufficient, semantic central and context positives would each increase from 2/15 to 3/15. Semantic answer-support Hit@3 would increase from 2/5 to 3/5 (0.40 to 0.60), a change of 0.20. Its answer-support MRR would increase from 0.30 to 0.40 because the additional answer appears at rank 2. Its rank-1 support would not change, nor would the selected high-score failure. Sentence-window context Hit@3 would remain higher at 4/5 (0.80); sentence-window central Hit@3 would tie semantic at 3/5 under that alternative judgment.

This review measures full answer availability in saved returned text. For long semantic chunks, that text may extend beyond the text represented by the embedding model's token limit; the separate truncation diagnostics must therefore be reported alongside these labels. A positive label does not establish that the answer-bearing passage influenced its retrieval score, and these five questions do not establish general retrieval performance.
