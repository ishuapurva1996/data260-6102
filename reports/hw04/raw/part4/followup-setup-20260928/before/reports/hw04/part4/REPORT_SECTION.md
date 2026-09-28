# Part 4 — Local retrieval-augmented generation

**Status: implementation and evidence are available; the required complete, supported, cited C answer remains incomplete.** The selected run contains all 18 main A/B/C answers and four additional sweep answers. All 22 calls completed normally. C refused Q5/Q6 with the exact required sentence, but it did not give a fully correct, supported, cited answer to an answerable question. The failed demonstration is retained in the verification receipt.

SID4 **6102** · PORT_BASE **8702** · PREFIX **s6102** · SEED **6102** · VERIFY_SEED **266102** · DOMAIN_ID **6** (Rental Housing Listings). Base revision `421c77ddca9ce998e5088dd305ea4da9bb714238`, branch `codex/hw4-part2-backend`, with uncommitted Part 4 additions. This section concerns the saved source snapshots. It does not assert that archived handbook rules are current policy.

## Corpus and actual index (R1)

The corpus has five distinct official housing documents. Four existing HW3 snapshots are reused byte-for-byte; the fifth is the EPA disclosure article downloaded for Part 4. Only those five allowlisted text files enter the index. Questions, answer keys, prior reports and experiment outputs are excluded. [The manifest](CORPUS_MANIFEST.json) records source URLs, dates, extraction notes, byte counts, original-file hashes and text hashes; [the source audit](source_audit.json) records the relevant passages.

| Source ID | Document/version | Clean UTF-8 bytes |
| --- | --- | --- |
| HUD_SELECTION | [HUD Handbook 4350.3 REV-1, Chapter 4: Waiting List and Tenant Selection](https://www.hud.gov/sites/documents/43503c4hsgh.pdf) — Archived 2013 PDF; pages contain 2007, 2009 and 2013 revision dates | 145418 |
| HUD_INCOME | [HUD Handbook 4350.3 REV-1, Chapter 5: Determining Income and Calculating Rent](https://www.hud.gov/sites/documents/43503c5hsgh.pdf) — Archived 2013 PDF; pages contain 2007, 2009 and 2013 revision dates | 160419 |
| EPA_LEAD | [Protect Your Family From Lead in Your Home](https://www.epa.gov/system/files/documents/2026-02/protectyourfamily_pamphlet_2026_3.pdf) — January 2026; federal authors EPA, CPSC and HUD | 21608 |
| HUD_FAIR | [Fair Housing: Equal Opportunity for All](https://www.hud.gov/sites/documents/fheo_booklet_eng.pdf) — Archived booklet; PDF metadata creation/modification June 6, 2011; publication date not asserted | 18414 |
| EPA_DISCLOSURE | [Real Estate Disclosures about Potential Lead Hazards](https://www.epa.gov/lead/real-estate-disclosures-about-potential-lead-hazards) — EPA web article, last updated May 27, 2026; frozen September 28, 2026 UTC | 6703 |

Total clean text: **352,562 bytes**. The added article was accessed September 28, 2026 UTC and identifies May 27, 2026 as its last update. Its original HTML, extraction script, HTTP headers and section offsets are retained. Page offsets for the four PDFs remain in the unchanged HW3 page map.

The documented size unit is **characters**, because the assignment does not specify a unit. The chunker uses at most 500 characters, prefers a nearby sentence/paragraph boundary, and requests 50 characters of overlap. Actual construction produced **925 chunks**: five first chunks with zero overlap, and 920 with exactly 50. The largest chunk has 500 characters and 194 MiniLM tokens, below the 256-token embedding limit. No overflow shortening, overlap deviations or silent truncations occurred. Each chunk retains exact text, source ID/title, page or section, character offsets, source hash and deterministic chunk ID. Version and URL resolve through its source ID in the manifest.

The real index is LlamaIndex `VectorStoreIndex` backed by `SimpleVectorStore`, with 925 normalized 384-dimensional MiniLM vectors. The embedding model is `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Its cache is explicit, and the experiment loads it offline. The final index took 21.102 seconds to build; this is one observation, not a benchmark.

[Chunk records](../raw/part4/scored-20260928-03/chunks.jsonl) · [Actual index audit](../raw/part4/scored-20260928-03/index_audit.json). The following genuine browser capture places the actual chunk/index code directly above its saved outputs.

![R1 code and actual corpus/index/chunk output](../screenshots/part4/scored-20260928-03/01-corpus-index-chunks.png)

## Configurations, calibration and provenance (R2–R3)

The CLI is `code/rag.py`, supported by `src/rag/pipeline.py`, `runner.py` and `evaluation.py`. The dedicated `.venv-rag` environment leaves the existing application environment unchanged. The selected generator is local Ollama 0.33.0 `qwen2.5:3b` (Q4_K_M), digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`, on an Apple M4 with 24 GiB RAM and macOS 15.7.4. All A/B/C and sweep calls use this same model, seed 6102, temperature 0, a 4096-token window, `think:false` and a 768-token output ceiling. Fresh requests carry no prior conversation. Model generation uses loopback only, with cloud disabled; setup downloaded only public assets.

| Configuration | Exact experimental treatment |
| --- | --- |
| A | The question alone, with no retrieved text, source labels or grounding instructions. |
| B | The raw top-k chunk texts in retrieval order, with a minimal instruction to answer using the supplied text. Main k=3. |
| C | The same raw candidates as B, filtered at similarity 0.50, conservatively deduplicated, ordered by descending score with deterministic ties, labeled with source metadata and constrained by explicit grounding rules. |

C reserves at most **1800 generator tokens** for evidence, including labels. Its pinned Qwen2.5 tokenizer counts actual evidence/prompt text; 128 tokens are separately reserved for the native serving template and 768 for the answer. All actual Ollama prompt counts fit these bounds. The exact refusal is `I cannot answer this question from the provided documents`. The prompt gives clarification precedence for underspecified questions, requires a source number for every factual claim, preserves qualifications, and prohibits prior-knowledge supplementation. It treats source content as evidence, not instructions.

The 0.50 cutoff was chosen using eight separate development questions and 40 annotated candidate hits. It retained a useful disclosure-record passage at about 0.513 while excluding unsupported development topics whose highest scores were about 0.487, 0.435 and 0.178. Other high-scoring development chunks still omitted requested facts, so similarity was not treated as proof of support. [Calibration](calibration.json) preserves the tested thresholds and annotations. Conservative duplicate detection preserves distinct numbers, negation, exceptions and scope; it never merges different sources merely because their topic overlaps.

Questions and answer evidence were frozen after actual chunk inspection and before scored generation. Runtime filtering and prompting never receive gold facts or question-ID-specific answers. Each scored run snapshots code, source text, question keys, calibration, model identities and settings. It reads the frozen source/question/configuration data while executing imported live code; matching start/end code hashes establish the executed version. Requests are saved before calls, and retrieved text/source/score lines are printed and flushed before generation. End-of-run hashes found no live generation-code or input changes.

The initial 1.7B run exposed two baseline output-limit stops and an overly conservative byte-based evidence budget. A matching generator tokenizer and a uniform 768-token ceiling were tested with separate development questions before the next freeze. A 4B thinking-template trial failed in development and was abandoned with its outputs/interruption record retained. The second 1.7B run and final 3B run each completed all 22 calls but still failed the supported C answer requirement. [The remediation record](REMEDIATION.md) explains these bounded attempts. Earlier runs are not mixed into the selected tables.

[Selected metadata and hashes](../raw/part4/scored-20260928-03/run_metadata.json) · [Exact requests](../raw/part4/scored-20260928-03/requests.jsonl) · [Retrieval records](../raw/part4/scored-20260928-03/retrievals.jsonl) · [Printed transcript](../raw/part4/scored-20260928-03/RUN_LOG.txt).

![R2 actual code and retrieval printed before generation](../screenshots/part4/scored-20260928-03/02-retrieval-before-generation.png)

## Six frozen questions and evidence proof (R4)

| ID/type | Exact question | Expected behavior |
| --- | --- | --- |
| Q1 / one_chunk | According to the archived HUD tenant-selection handbook, how many days does an applicant have to request a meeting to dispute a rejection? | answer |
| Q2 / two_chunks | According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take? | answer |
| Q3 / overlapping_sources | According to the supplied documents, what information about known lead-based paint hazards should a prospective renter of covered pre-1978 housing receive before signing a lease? | answer |
| Q4 / ambiguous | How long do I have to file? | clarify |
| Q5 / absent_answer | What is the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026? | refuse |
| Q6 / unrelated | Who won the 2022 FIFA World Cup? | refuse |

Q1's 14-day rule fits in one actual chunk. Q2 was narrowed before scored retrieval/generation because the initial full inspection definition crossed two chunks and would have required three with the risk definition. The final question asks for paint presence/location and current hazards/actions. Its proof finds no single sufficient chunk anywhere in the five-source index and identifies this sufficient pair:

- `EPA_LEAD:3830114fcc78:0008845-0009262` — inspection presence/location.
- `EPA_LEAD:3830114fcc78:0009535-0009993` — current hazards and actions.

A separate full-corpus semantic check found that the nearby combined-inspection passage omits the requested actions, so it is not a single-chunk substitute. Q3 requires known lead information **and** available records/reports; equivalent EPA passages are alternatives within each fact group. Q4 requires clarification. Q5's property/date and Q6's sports result have no supporting corpus passage. See [questions and exact gold spans](questions.yaml), [preflight review](preflight_review.json), and the selected [coverage audit](../raw/part4/scored-20260928-03/gold_chunk_audit.json).

## Evaluation definitions and main results (R6)

The evaluator is the Codex assistant, with a separate semantic-review worker; student review is not claimed. Each judgment records reasons and exact support quotes from the actual supplied context. Automated checks establish artifact consistency, quote presence and valid source-number membership, not the truth of the semantic judgment.

- **Correct retrieval:** all essential evidence groups appear in the raw candidates, assessed for Q1–Q3 only. A source-file match is insufficient. Final-context coverage applies the same rule after C's filtering.
- **Accuracy:** complete correct answer for Q1–Q3, clarification for Q4, and semantic refusal for Q5/Q6, divided by six. Answerable-only accuracy is also shown.
- **Faithfulness:** supported factual claims divided by all factual claims in main B/C answers. Repeated propositions count once. A is N/A because no context is supplied. A response with zero factual claims is N/A, not perfectly faithful.
- **Grounded answer:** every factual claim is supported by its cited supplied evidence. A correct remembered fact or a syntactically valid citation does not establish grounding.
- **Format compliance:** source-number format for factual answers, a clarifying question, or the exact refusal as applicable. This common target is stricter than the instructions given to A/B, so the comparison is descriptive rather than an isolated prompt-effect test.
- **Robustness:** correct behavior on Q4–Q6 divided by three. Semantic refusal and exact refusal are reported separately. N/A is distinct from false.

| Configuration | Retrieval Q1–Q3 | Accuracy all six | Answerable Q1–Q3 | Faithful claims | Format | Robustness Q4–Q6 | Refusal Q5/Q6 | Exact refusal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | N/A | 2/6 | 0/3 | N/A | 1/6 | 2/3 | 1/2 | 0/2 |
| B | 1/3 | 3/6 | 2/3 | 9/11 | 0/6 | 1/3 | 1/2 | 0/2 |
| C | 1/3 | 2/6 | 0/3 | 3/5 | 4/6 | 2/3 | 2/2 | 2/2 |

Raw and final evidence coverage are both 1/3 for B and C. The next table records every main question/configuration. A grounded N/A means no factual answer to assess; it does not mean the question was answered successfully.

| Response | Correct retrieval | Final coverage | Correct answer | Grounded | Refused when needed |
| --- | --- | --- | --- | --- | --- |
| Q1-A-k0 | N/A | N/A | No | No | N/A |
| Q1-B-k3 | No | No | No | No | N/A |
| Q1-C-k3 | No | No | No | N/A | N/A |
| Q2-A-k0 | N/A | N/A | No | No | N/A |
| Q2-B-k3 | No | No | Yes | No | N/A |
| Q2-C-k3 | No | No | No | No | N/A |
| Q3-A-k0 | N/A | N/A | No | No | N/A |
| Q3-B-k3 | Yes | Yes | Yes | No | N/A |
| Q3-C-k3 | Yes | Yes | No | N/A | N/A |
| Q4-A-k0 | N/A | N/A | Yes | N/A | N/A |
| Q4-B-k3 | N/A | N/A | No | No | N/A |
| Q4-C-k3 | N/A | N/A | No | N/A | N/A |
| Q5-A-k0 | N/A | N/A | Yes | No | Yes |
| Q5-B-k3 | N/A | N/A | Yes | No | Yes |
| Q5-C-k3 | N/A | N/A | Yes | N/A | Yes |
| Q6-A-k0 | N/A | N/A | No | No | No |
| Q6-B-k3 | N/A | N/A | No | No | No |
| Q6-C-k3 | N/A | N/A | Yes | N/A | Yes |

Q1 fails retrieval for B/C; all three selected responses abstain. For Q2, B states the required distinction correctly but its inspection fact is not supported by the actual candidates. C's “where both are located” imports combined-procedure wording and fails the full distinction. Q3 is retrieved completely: B gives the essential information without citations, while C outputs only `[1]`. A alone clarifies Q4. All configurations decline Q5. A and B answer Q6 from memory, which is a failure of the required refusal behavior; C refuses exactly. No C answer meets all three conditions of completeness, actual evidence support and correct citation attribution.

[All claim-level judgments](../raw/part4/scored-20260928-03/judgments.json) · [Evaluation CSV](../raw/part4/scored-20260928-03/evaluation.csv) · [Exact A/B/C answer comparison](../raw/part4/scored-20260928-03/comparison.csv) · [Summary CSV](../raw/part4/scored-20260928-03/evaluation_summary.csv).

![R6 code and saved evaluation summary](../screenshots/part4/scored-20260928-03/03-evaluation-summary.png)

## Context sweep (R5)

Q2 is identical at k=1,3,5. B and C use the same candidates at each k; only the four k=1/k=5 calls are additional generations. The k=3 rows below reference the existing main responses. No chunk size, model, threshold or prompt changes occur within the sweep.

| Config/k | Reuse main | Returned/retained | Evidence tokens | Actual prompt/output tokens | Generation s | Full evidence | Correct answer | Grounded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B/1 | False | 1/1 | 96 | 171/87 | 4.122 | False | False | False |
| B/3 | True | 3/3 | 273 | 348/116 | 8.315 | False | True | False |
| B/5 | False | 5/5 | 436 | 511/71 | 6.068 | False | False | False |
| C/1 | False | 1/1 | 156 | 342/60 | 3.433 | False | False | False |
| C/3 | True | 3/3 | 465 | 651/62 | 6.405 | False | False | False |
| C/5 | False | 5/5 | 760 | 946/50 | 7.573 | False | False | False |

At k=1, only the risk-assessment passage appears. k=3 adds a buyer inspection-opportunity passage and a combined-procedure passage; neither supplies the missing standalone inspection definition. k=5 adds disclosure-form and records/report material rather than the needed definition. Thus unrelated-to-the-required-fact text already appears at k=3 and increases at k=5. C retains all 1/3/5 candidates for Q2; the 0.50 threshold does not remove these topical distractors. No deduplication or budget drop occurs in the final sweep.

**No k wins under the complete-and-supported-answer criterion.** B k=3 is the only sweep answer credited correct against the full-corpus key, but it lacks actual-context support and citations. C k=5 omits paint location and cites the combined-procedure passage for risk facts supplied elsewhere. Additional context did not repair retrieval. These single-call timings are observations, not reliable latency rankings. Across all 22 calls, generation ranged from 0.762 to 33.613 seconds; no performance claim is inferred.

[The six-row sweep CSV](../raw/part4/scored-20260928-03/k_sweep.csv) preserves all answers, chunk IDs, token counts, timings and reasons. The screenshot appendix below includes four extra outputs and explicitly reuses the two main k=3 captures.

## Analysis (R7; 300–500 words)
<!-- ANALYSIS_START -->
Retrieval-augmented generation first finds document passages and then asks a model to answer from them. This experiment shows why both stages need checking. The index contained the correct fourteen-day rejection deadline, but the top three results did not. B and C therefore lacked the needed fact. C declined safely, yet that still counted as an incorrect answer to an answerable question.

Q3 separated retrieval quality from generation quality. The retrieved passages contained both required facts: disclose known lead information and provide available records and reports. B included them but supplied no citations. C received the same essential evidence with labels and returned only “[1].” A citation by itself is not an answer. This failure remained visible rather than being repaired in the saved output.

For Q2, increasing k from one to three and five never retrieved the standalone inspection definition. The first passage explained risk assessment; extra passages discussed a combined procedure, buyer inspection opportunities, and disclosure paperwork. B at k=3 stated the right distinction, but the supplied context did not support its standalone inspection claim. C mixed procedure wording at k=3 and omitted paint location at k=5. No setting produced a complete supported answer, so the sweep has no defensible winner.

The engineered context did help enforce the two required refusals. C rejected both the unknown apartment rent and the unrelated sports question exactly. A and B answered the sports question from memory, violating the required behavior even though naming the winner could be true. C also refused the ambiguous filing question instead of asking for clarification, despite an explicit instruction to clarify first. Conservative refusal alone is therefore insufficient.

The fixed 500-character chunks and 50-character overlap kept every embedding below its token limit. They also split related definitions across chunks. Because chunk size was not varied, these observations do not prove that another size would improve retrieval. Source metadata made citations traceable, but C still cited insufficient evidence. Ordering and source labels were not tested independently. No duplicate or token-budget removals occurred in the selected run; the relevance filter removed nine low-scoring candidates across Q4–Q6, including all their C context.

The selected main accuracy was A 2/6, B 3/6 and C 2/6. Supported claims were B 9/11 and C 3/5. These small denominators limit generalization. Earlier failures, development calibration and bounded model changes are preserved. The remaining task is to demonstrate a complete cited C answer with a general improvement tested on development questions, then repeat the full frozen comparison without changing the scoring rules.
<!-- ANALYSIS_END -->

## Verification and limitations (R8)

Focused tests: **28 passed**. They cover source allowlisting/hash checks, character/token limits, overlap, protected deduplication distinctions, context budgets, A/B/C isolation, failed/missing records, evidence coverage, claim/citation checks, N/A denominators, exact refusals, sweep reuse and integrity failures. The source files also compile. [Test output](../raw/part4/setup/tests-delivery-28.txt).

All 22 selected calls finished with `done_reason=stop`, no transport errors, no output-limit stops and no prompt overflow. The final [verification receipt](verification.json) passes **11/12 checks** and reports the failed required C answer demonstration. All other evidence, matrix, integrity, report and screenshot checks pass. The [handoff](HANDOFF.md) gives exact setup, run, evaluation, capture and verification commands. Shared metrics, run log and AI-use disclosure receive additive Part 4 entries. Existing application code, databases and Parts 1–3 evidence are preserved; the old benchmark was not rerun.

## Genuine code/output captures and unedited answers (R3–R5, R8)

These PNGs are **actual Chromium screenshots of saved local experiment records**, not live terminal or chat screenshots. Each image labels that distinction and places the frozen prompt-building code immediately above the unedited answer. Full prompts, source mappings and context decisions remain in the image/HTML and raw JSON. The [capture manifest](../screenshots/part4/scored-20260928-03/manifest.json) records hashes, timestamps, browser version, source lines and exact-text/overflow checks. Long images should be split into readable pages during later PDF assembly; that PDF is not assembled here.

### Q1-A-k0 — main

According to the archived HUD tenant-selection handbook, how many days does an applicant have to request a meeting to dispute a rejection?

Correct answer: **No**; grounded: **No**. Incorrect for this answerable corpus question: does not provide the archived 14-day deadline.

Unedited model response:

```text
I'm sorry, but I don't have direct access to an archived HUD tenant-selection handbook or any specific document to provide you with the exact information you're looking for. The handbook or any relevant document might contain this information, but without direct access to it, I can't provide the specific number of days.

Typically, such information is found in the terms and conditions or the dispute resolution process section of the handbook. If you have the handbook or can access it, you should be able to find this information within the dispute resolution or appeal process section.

If you need this information urgently, I recommend checking the handbook or contacting the relevant authority or department for the most accurate and up-to-date information.
```

![Q1-A-k0 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q1-A-k0.png)

### Q1-B-k3 — main

According to the archived HUD tenant-selection handbook, how many days does an applicant have to request a meeting to dispute a rejection?

Correct answer: **No**; grounded: **No**. Incorrect for the answerable corpus question: abstains and omits the 14-day deadline because raw retrieval missed it.

Unedited model response:

```text
The provided text does not contain information about how many days an applicant has to request a meeting to dispute a rejection. The text discusses tenant selection plans, reconsideration of previously denied applicants, and retention of forms, but does not specify a timeframe for disputing a rejection.
```

![Q1-B-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q1-B-k3.png)

### Q1-C-k3 — main

According to the archived HUD tenant-selection handbook, how many days does an applicant have to request a meeting to dispute a rejection?

Correct answer: **No**; grounded: **N/A**. Incorrect for the answerable corpus question: refuses after retrieval missed the 14-day deadline. Appropriate evidence caution does not repair answer accuracy.

Unedited model response:

```text
I cannot answer this question from the provided documents
```

![Q1-C-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q1-C-k3.png)

### Q2-A-k0 — main

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct answer: **No**; grounded: **No**. Incorrect: adds procedural claims not established by the frozen pamphlet and blurs paint inspection with dust/soil assessment. The answer treats deteriorated/chipped/peeling appearance as signs of lead-based paint, while the saved pamphlet describes XRF or laboratory paint testing for inspection and separate paint/dust/soil sampling for risk assessment. It does not preserve that distinction.

Unedited model response:

```text
The EPA pamphlet, specifically the "EPA Lead-Based Paint Hazard Information" pamphlet, provides guidance on lead-based paint inspections and risk assessments. Here's a breakdown of what each of these involves:

### Lead-Based Paint Inspection
A lead-based paint inspection is a process used to identify the presence of lead-based paint in a home or building. This inspection typically involves the following steps:

1. **Visual Inspection**: The inspector looks for paint that appears to be deteriorated, chipped, or peeling, as these are common signs of lead-based paint. They also check for paint that is in good condition but is located in areas where lead-based paint is known to be present, such as older homes or buildings.

2. **Surface Sampling**: If deteriorated paint is found, the inspector may take samples of the paint to test for lead content. This is done using a small, sharp tool to scrape off a small amount of paint and then using a laboratory test to determine if the paint contains lead.

3. **Environmental Sampling**: In some cases, especially in older buildings, the inspector may also take samples of dust and soil to check for lead contamination. This is because lead can also be found in dust and soil, especially in areas where lead-based paint has deteriorated.

### Risk Assessment
A risk assessment is a process used to evaluate the potential health risks associated with lead-based paint and to determine appropriate actions to mitigate those risks. The risk assessment typically involves the following steps:

1. **Identify Lead-Based Paint**: The risk assessment starts by identifying the areas where lead-based paint is present, based on the results of the lead-based paint inspection.

2. **Assess Risks**: The risk assessment evaluates the potential health risks associated with lead exposure. This includes assessing the likelihood of children or adults coming into contact with lead-based paint and the potential for lead to be ingested or inhaled.

3. **Determine Actions**: Based on the results of the risk assessment, the inspector or professional will determine the appropriate actions to take. These actions may include:

   - **Paint Removal**: If the risk assessment indicates that the lead-based paint is in a condition that poses a significant risk, the inspector may recommend removing the paint to reduce the risk of lead exposure.

   - **Paint Shielding**: In some cases, the inspector may recommend painting over the lead-based paint to prevent the release of lead into the environment.

   - **Environmental Controls**: If lead-contaminated dust or soil is found, the inspector may recommend measures to control the spread of lead dust and soil, such as sealing off areas where lead-based paint is present.

   - **Lead Safe Work Practices**: The inspector may also recommend following lead-safe work practices to minimize the risk of lead exposure during any work that disturbs lead-based paint.

4. **Monitor and Follow-Up**: The risk assessment process often includes monitoring the effectiveness of the actions taken and following up to ensure that the lead-based paint is properly managed and that the risk of lead exposure is minimized.

In summary, a lead-based paint inspection identifies the presence of lead-based paint, while a risk assessment evaluates the potential health risks associated with lead exposure and determines appropriate actions to mitigate those risks.
```

![Q2-A-k0 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q2-A-k0.png)

### Q2-B-k3 — main

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct answer: **Yes**; grounded: **No**. Correct against the frozen answer key: distinguishes paint presence/location from current hazards and actions. The added surface examples do not change that distinction. Accuracy can be true while actual-context faithfulness fails.

Unedited model response:

```text
According to the EPA pamphlet, a lead-based paint inspection typically locates areas in a home that have lead-based paint, while a risk assessment identifies any lead hazards present, such as from paint, dust, or soil, and what actions are needed to address these hazards.

Specifically:
- A lead-based paint inspection can locate areas with lead-based paint, such as doors, windows, floors, stairs, and walls.
- A risk assessment identifies any lead hazards, including from dust near painted surfaces and bare soil in the yard, and provides recommendations for addressing these hazards.
```

![Q2-B-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q2-B-k3.png)

### Q2-C-k3 — main

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct answer: **No**; grounded: **No**. Incorrect under the full-qualification rubric: the inspection sentence imports ambiguous "where both are located" wording from a combination procedure and does not preserve the standalone inspection/risk-assessment distinction. Its risk-assessment clause is correct.

Unedited model response:

```text
A lead-based paint inspection by a certified inspector tells you if your home has any lead-based paint and where both are located [3]. A lead-based paint risk assessment identifies if your home currently has any lead hazards from paint, dust or soil, and what actions to take to address any hazards [1].
```

![Q2-C-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q2-C-k3.png)

### Q3-A-k0 — main

According to the supplied documents, what information about known lead-based paint hazards should a prospective renter of covered pre-1978 housing receive before signing a lease?

Correct answer: **No**; grounded: **No**. Incorrect: invents a standardized LP-HIN form and several disclosure duties not in the frozen source; does not clearly require all available records/reports. General known-hazard wording does not satisfy the full key.

Unedited model response:

```text
When a prospective renter is considering a lease for pre-1978 housing, they should be provided with information about any known lead-based paint hazards. This information is crucial to ensure the safety of the tenant and should be provided in a clear and accessible manner. Here are some key points that should be included in the information:

1. **Lead-Based Paint Hazard Information and Notification (LP-HIN) Form**: The landlord should provide the prospective renter with a copy of the LP-HIN form, which is a standardized document that outlines the known lead-based paint hazards in the property. This form should be completed by the landlord and provided to the prospective renter before the lease is signed.

2. **Description of Hazards**: The information should include a detailed description of any known lead-based paint hazards, such as peeling or chipping paint, deteriorated paint, or areas where lead-based paint may be present. It should also specify the rooms or areas where these hazards are located.

3. **Remediation and Abatement Information**: The landlord should provide information about any remediation or abatement work that has been done to address lead-based paint hazards. This could include the date of the last inspection, the results of any lead dust tests, and the steps taken to prevent lead exposure.

4. **Precautionary Measures**: The information should include instructions on how to minimize exposure to lead-based paint hazards. This might include recommendations for cleaning methods, the use of protective equipment, and the importance of maintaining good indoor air quality.

5. **Lead-Based Paint Disclosure**: The landlord should disclose whether the property has been inspected for lead-based paint hazards and whether any remediation or abatement work has been completed. This disclosure should be provided in a clear and understandable manner.

6. **Additional Resources**: The landlord should provide information about additional resources available to tenants, such as local health departments, environmental agencies, or community organizations that can provide further assistance and guidance.

7. **Legal Rights and Responsibilities**: The information should include a summary of the legal rights and responsibilities of both the landlord and the tenant regarding lead-based paint hazards. This might include information about the landlord's obligation to maintain the property in a safe condition and the tenant's right to a safe living environment.

By providing this comprehensive information, the landlord ensures that the prospective renter is fully informed and can make an informed decision about whether to proceed with the lease.
```

![Q3-A-k0 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q3-A-k0.png)

### Q3-B-k3 — main

According to the supplied documents, what information about known lead-based paint hazards should a prospective renter of covered pre-1978 housing receive before signing a lease?

Correct answer: **Yes**; grounded: **No**. Correct: includes both essential known-information and available-record/report groups, adds a supported warning statement, and preserves covered-housing scope from the question without inventing a renter inspection right.

Unedited model response:

```text
According to the supplied documents, a prospective renter of covered pre-1978 housing should receive information about known lead-based paint hazards. Specifically, the renter should receive a disclosure of known information about the presence of lead-based paint or lead-based paint hazards, or be informed that there are none. They should also receive all available records and reports on lead-based paint and lead-based paint hazards, or be informed that there are none. Additionally, a specific warning statement about lead-based paint should be included.
```

![Q3-B-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q3-B-k3.png)

### Q3-C-k3 — main

According to the supplied documents, what information about known lead-based paint hazards should a prospective renter of covered pre-1978 housing receive before signing a lease?

Correct answer: **No**; grounded: **N/A**. Incorrect: the entire unedited answer is only [1], with no answer to either required information group.

Unedited model response:

```text
[1]
```

![Q3-C-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q3-C-k3.png)

### Q4-A-k0 — main

How long do I have to file?

Correct answer: **Yes**; grounded: **N/A**. Correct: asks what filing means and offers possible processes as questions rather than asserting a deadline.

Unedited model response:

```text
The term "file" can refer to different things depending on the context. Could you please specify what you mean by "file"? Are you referring to filing a legal case, submitting an academic assignment, or something else? Providing more context will help me give you a more accurate and helpful response.
```

![Q4-A-k0 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q4-A-k0.png)

### Q4-B-k3 — main

How long do I have to file?

Correct answer: **No**; grounded: **No**. Incorrect: recognizes it cannot give a deadline but never asks what action or process the user means. Q4 requires clarification, not only refusal.

Unedited model response:

```text
Based on the information provided in the text, the duration for filing is not explicitly stated. The text discusses various aspects of tenant files, confidentiality, and retention periods for documents, but does not specify a filing deadline. Therefore, I cannot answer "How long do I have to file?" with the given information.
```

![Q4-B-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q4-B-k3.png)

### Q4-C-k3 — main

How long do I have to file?

Correct answer: **No**; grounded: **N/A**. Incorrect: refuses rather than following the ambiguity-precedence rule and asking which process is meant.

Unedited model response:

```text
I cannot answer this question from the provided documents
```

![Q4-C-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q4-C-k3.png)

### Q5-A-k0 — main

What is the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026?

Correct answer: **Yes**; grounded: **No**. Correct handling: declines to supply the missing rent amount and directs the user to the property.

Unedited model response:

```text
I don't have real-time data access or the ability to search for specific properties like Cedar Grove Apartments. To find the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026, you would need to contact the property directly or visit their official website or contact their leasing office. They would have the most accurate and up-to-date information regarding their rental rates and availability.
```

![Q5-A-k0 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q5-A-k0.png)

### Q5-B-k3 — main

What is the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026?

Correct answer: **Yes**; grounded: **No**. Correct handling: does not invent a rent amount and explicitly says the specific property/date fact is unavailable.

Unedited model response:

```text
I do not have enough information in the provided text to determine the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026. The text does not contain any details about Cedar Grove Apartments or Unit 4B. It discusses various housing subsidy and rent-related topics, but does not provide specific information about this particular property or date.
```

![Q5-B-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q5-B-k3.png)

### Q5-C-k3 — main

What is the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026?

Correct answer: **Yes**; grounded: **N/A**. Correct handling: gives no absent/unrelated answer and uses the required exact refusal.

Unedited model response:

```text
I cannot answer this question from the provided documents
```

![Q5-C-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q5-C-k3.png)

### Q6-A-k0 — main

Who won the 2022 FIFA World Cup?

Correct answer: **No**; grounded: **No**. Incorrect handling: supplies a remembered winner and extra match/title claims instead of refusing this unsupported sports question.

Unedited model response:

```text
The 2022 FIFA World Cup was won by Argentina. They defeated France in the final match with a score of 3-0. This victory marked Argentina's third World Cup title, following their wins in 1978 and 1986.
```

![Q6-A-k0 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q6-A-k0.png)

### Q6-B-k3 — main

Who won the 2022 FIFA World Cup?

Correct answer: **No**; grounded: **No**. Incorrect handling: supplies Argentina after saying the text cannot answer. The final recalled answer defeats refusal regardless of the winner’s truth.

Unedited model response:

```text
The provided text does not contain information about who won the 2022 FIFA World Cup. The text discusses various financial and legal scenarios related to assets, income, and trusts. To answer the question about the 2022 FIFA World Cup winner, I would need to look up current sports news, which I do not have access to. Based on current knowledge, the winner of the 2022 FIFA World Cup was Argentina.
```

![Q6-B-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q6-B-k3.png)

### Q6-C-k3 — main

Who won the 2022 FIFA World Cup?

Correct answer: **Yes**; grounded: **N/A**. Correct handling: gives no absent/unrelated answer and uses the required exact refusal.

Unedited model response:

```text
I cannot answer this question from the provided documents
```

![Q6-C-k3 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q6-C-k3.png)

### Q2-B-k1 — sweep

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct answer: **No**; grounded: **No**. Incorrect: treats inspection as hazard assessment and uses risk-assessor sampling targets as its definition.

Unedited model response:

```text
According to the EPA pamphlet, a lead-based paint inspection locates any lead hazards in a home, specifically focusing on deteriorated paint on doors, windows, floors, stairs, and walls. On the other hand, a risk assessment identifies any lead hazards in a home, including those from dust near painted surfaces and bare soil in the yard. A risk assessment also identifies what actions need to be taken to address any identified hazards.
```

![Q2-B-k1 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q2-B-k1.png)

### Q2-C-k1 — sweep

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct answer: **No**; grounded: **No**. Incorrect: transfers a risk-assessment sampling task to inspection instead of answering paint presence/location.

Unedited model response:

```text
According to the EPA pamphlet, a lead-based paint inspection locates deteriorated paint on doors, windows, floors, stairs, and walls. A risk assessment identifies if the home currently has any lead hazards from paint, dust, or soil, and what actions to take to address any hazards.
```

![Q2-C-k1 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q2-C-k1.png)

### Q2-B-k5 — sweep

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct answer: **No**; grounded: **No**. Incorrect: conflates inspection with hazard assessment and imports surface-condition disclosure material as an inspection definition.

Unedited model response:

```text
According to the EPA pamphlet, a lead-based paint inspection typically locates lead-based paint hazards in the home or building, including the location of the lead-based paint and the condition of the painted surfaces. On the other hand, a risk assessment identifies any lead hazards in the home or building and what actions need to be taken to address these hazards.
```

![Q2-B-k5 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q2-B-k5.png)

### Q2-C-k5 — sweep

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct answer: **No**; grounded: **No**. Incomplete: omits the requested location of lead-based paint from the inspection definition. Its risk-assessment clause is correct.

Unedited model response:

```text
A lead-based paint inspection tells you if your home has any lead-based paint, and a risk assessment identifies if your home currently has any lead hazards from paint, dust or soil, and what actions to take to address any hazards. [3]
```

![Q2-C-k5 actual frozen code and unedited output](../screenshots/part4/scored-20260928-03/Q2-C-k5.png)

The sweep's k=3 references reuse [Q2-B-k3](../screenshots/part4/scored-20260928-03/Q2-B-k3.png) and [Q2-C-k3](../screenshots/part4/scored-20260928-03/Q2-C-k3.png) above; they are not additional calls or captures. The four k=1/k=5 images are distinct calls. Together with setup, retrieval and evaluation, the inventory has 25 genuine PNG captures for 22 distinct answers.
