# HW3 Part 2 retrieval metrics

Run: `manual-screenshots-20260921`

Top-1 cosine means the **maximum explicit cosine among returned hits**, as defined in the assignment; it may differ from the store's rank-1 cosine. Mean@k uses the actual returned hits. Source Recall@k counts unique expected source IDs, not chunks. Central and context answer support are manual judgments; a source hit alone does not prove an answer.

Question-level macro averages; diagnostics excluded from baseline. Null cosine values are excluded only from cosine averages and their denominator is explicit. Empty retrieval counts as zero source recall and answer support.

Retrieval latency includes only searches with a precomputed query vector; query embedding, index building, document re-embedding, and printing are excluded.

## Baseline questions

Questions: 5.

| Technique | Chunks | Avg central chars | Top-1 cosine | Mean@k cosine | Source Recall@k | Central support@k | Context support@k | Search ms | Cosine n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| semantic | 143 | 2406.3 | 0.6445 | 0.5708 | 1.0000 | 0.4000 | 0.4000 | 1.321 | 5 |
| sentence_window | 2735 | 125.8 | 0.7486 | 0.6997 | 1.0000 | 0.6000 | 0.8000 | 20.176 | 5 |
| token | 440 | 936.7 | 0.6850 | 0.6476 | 1.0000 | 0.2000 | 0.2000 | 3.435 | 5 |

### Per-question results

| Question | Technique | Returned/requested k | Top-1 cosine | Store rank-1 cosine | Mean@k cosine | Source Recall@k | Central support@k | Context support@k | Search ms | Samples |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1 | semantic | 3/3 | 0.5590 | 0.5590 | 0.5483 | 1.0000 | 1 | 1 | 1.321 | 10 |
| Q1 | sentence_window | 3/3 | 0.7134 | 0.7134 | 0.6710 | 1.0000 | 1 | 1 | 20.116 | 10 |
| Q1 | token | 3/3 | 0.6075 | 0.6075 | 0.5859 | 1.0000 | 0 | 0 | 3.476 | 10 |
| Q2 | semantic | 3/3 | 0.7438 | 0.7438 | 0.6400 | 1.0000 | 0 | 0 | 1.310 | 10 |
| Q2 | sentence_window | 3/3 | 0.7175 | 0.7175 | 0.6818 | 1.0000 | 0 | 0 | 20.145 | 10 |
| Q2 | token | 3/3 | 0.7511 | 0.7511 | 0.7019 | 1.0000 | 0 | 0 | 3.486 | 10 |
| Q3 | semantic | 3/3 | 0.6881 | 0.6881 | 0.5227 | 1.0000 | 1 | 1 | 1.331 | 10 |
| Q3 | sentence_window | 3/3 | 0.7603 | 0.7603 | 0.6989 | 1.0000 | 0 | 1 | 20.100 | 10 |
| Q3 | token | 3/3 | 0.6783 | 0.6783 | 0.5982 | 1.0000 | 1 | 1 | 3.452 | 10 |
| Q4 | semantic | 3/3 | 0.6646 | 0.6646 | 0.5866 | 1.0000 | 0 | 0 | 1.317 | 10 |
| Q4 | sentence_window | 3/3 | 0.7592 | 0.7592 | 0.7499 | 1.0000 | 1 | 1 | 20.199 | 10 |
| Q4 | token | 3/3 | 0.7209 | 0.7209 | 0.6989 | 1.0000 | 0 | 0 | 3.380 | 10 |
| Q5 | semantic | 3/3 | 0.5672 | 0.5672 | 0.5564 | 1.0000 | 0 | 0 | 1.326 | 10 |
| Q5 | sentence_window | 3/3 | 0.7927 | 0.7927 | 0.6969 | 1.0000 | 1 | 1 | 20.318 | 10 |
| Q5 | token | 3/3 | 0.6672 | 0.6672 | 0.6530 | 1.0000 | 0 | 0 | 3.380 | 10 |

## Diagnostic questions

Questions: 0.

No saved questions in this group.

## Confident rank-1 failures

Predeclared criterion: store rank 1, explicit cosine ≥ 0.50, and manual answer support false in both central text and available context.

- **Q1 / semantic** (baseline): cosine 0.5590; source `HUD_INCOME`, node `semantic:f58b648d83a6c2ff:000060`. Evidence: Central exact quote: “Owner-created verification forms and the forms HUD-9887 and *HUD-9887-A* expire 15 months after they are signed.” Context exact quote: “Owner-created verification forms and the forms HUD-9887 and *HUD-9887-A* expire 15 months after they are signed.” Rationale: This passage gives validity periods for verification forms and limits on historical income information. It does not give a rejected applicant’s 14-day meeting-request period in either text.
- **Q1 / token** (baseline): cosine 0.6075; source `HUD_FAIR`, node `token:e8dcdb0274d129da:000012`. Evidence: Central exact quote: “Notify you and the respondent if HUD cannot complete its investigation within 100 days of filing your complaint” Context exact quote: “Notify you and the respondent if HUD cannot complete its investigation within 100 days of filing your complaint” Rationale: The passage concerns HUD complaint investigation and conciliation. The 100 days concerns investigation progress, not a rental applicant’s time to request a rejection meeting. Neither text provides the 14-day request deadline.
- **Q2 / semantic** (baseline): cosine 0.7438; source `HUD_INCOME`, node `semantic:f58b648d83a6c2ff:000000`. Evidence: Central exact quote: “Section 2: Determining Adjusted Income describes the procedures and requirements for determining adjusted income based on allowable deductions.” Context exact quote: “Section 2: Determining Adjusted Income describes the procedures and requirements for determining adjusted income based on allowable deductions.” Rationale: This introductory overview identifies a section about deductions but does not state the deduction per dependent or $480 amount. A section pointer is not the requested answer in either text.
- **Q2 / sentence_window** (baseline): cosine 0.7175; source `HUD_INCOME`, node `sentence_window:f58b648d83a6c2ff:001332`. Evidence: Central exact quote: “Tenant Rent Formulas” Context exact quote: “Tenant Rent Formulas” Rationale: The central text is a title and a URL. The window adds other fact-sheet references, but neither contains the $480 dependent-deduction rule. Following the external link would introduce evidence outside this retrieved text.
- **Q2 / token** (baseline): cosine 0.7511; source `HUD_INCOME`, node `token:f58b648d83a6c2ff:000000`. Evidence: Central exact quote: “The amount of assistance paid on behalf of the family is calculated using the family’s annual income less allowable deductions.” Context exact quote: “The amount of assistance paid on behalf of the family is calculated using the family’s annual income less allowable deductions.” Rationale: The text explains that deductions affect annual income and assistance, but it never specifies a dependent deduction or its $480 amount. Both texts are therefore related but insufficient.
- **Q4 / semantic** (baseline): cosine 0.6646; source `HUD_FAIR`, node `semantic:e8dcdb0274d129da:000005`. Evidence: Central exact quote: “You must file your lawsuit within two (2) years of the most recent date of alleged discriminatory action.” Context exact quote: “You must file your lawsuit within two (2) years of the most recent date of alleged discriminatory action.” Rationale: The full passage covers dismissal, reconsideration, private civil lawsuits and enforcement. It gives the private-lawsuit deadline but never states the one-year HUD-complaint deadline; same-topic retrieval is insufficient.
- **Q4 / token** (baseline): cosine 0.7209; source `HUD_FAIR`, node `token:e8dcdb0274d129da:000021`. Evidence: Central exact quote: “You must file your lawsuit within two (2) years of the most recent date of alleged discriminatory action.” Context exact quote: “You must file your lawsuit within two (2) years of the most recent date of alleged discriminatory action.” Rationale: The passage gives a two-year deadline for a private civil lawsuit, a different procedure from filing a complaint with HUD. Neither text states the one-year HUD-complaint deadline or its occurred-or-ended trigger.
- **Q5 / semantic** (baseline): cosine 0.5672; source `HUD_SELECTION`, node `semantic:d1f9239a9a35969b:000023`. Evidence: Central exact quote: “In the Section 8, RAP, and Rent Supplement programs, owners may not establish a minimum income requirement for applicants.” Context exact quote: “In the Section 8, RAP, and Rent Supplement programs, owners may not establish a minimum income requirement for applicants.” Rationale: This concerns whether an owner may require an applicant to have a minimum income. It does not give the percentage of available assisted units reserved through income targeting, so both texts lack the 40% rule.
- **Q5 / token** (baseline): cosine 0.6672; source `HUD_SELECTION`, node `token:d1f9239a9a35969b:000004`. Evidence: Central exact quote: “These regulations are applicable only to the Section 8 project-based program except where otherwise noted.” Context exact quote: “These regulations are applicable only to the Section 8 project-based program except where otherwise noted.” Rationale: The text lists regulatory references for income targeting and preferences. It does not give the minimum 40% share of assisted units becoming available during a project fiscal year.

## Retrieval diagnostics

All recorded queries returned the requested k.

Full chunk lengths, token lengths, truncation audit, manual annotations, and raw result texts remain in the run artifacts. These tables are regenerated offline with `code/retrieval_summarize.py`.
