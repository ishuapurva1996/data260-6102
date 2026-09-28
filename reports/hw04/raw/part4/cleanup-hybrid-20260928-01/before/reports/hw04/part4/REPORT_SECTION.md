# Part 4 — Local retrieval-augmented generation

**The focused follow-up is complete locally.** The selected run `scored-20260928-04` retains 18 main A/B/C answers and four additional sweep answers, plus eight auxiliary clarification decisions. All 30 local calls ended normally. C now gives a complete, supported, cited Q3 answer, clarifies Q4, and refuses Q5/Q6 exactly. A successful cited C answer is **our reviewed plan's completion criterion**, not an explicit assignment minimum. Q1/Q2 failures remain in the results.

SID4 **6102** · PORT_BASE **8702** · PREFIX **s6102** · SEED **6102** · VERIFY_SEED **266102** · DOMAIN_ID **6**. Branch `codex/hw4-part2-backend`; unchanged base HEAD `421c77ddca9ce998e5088dd305ea4da9bb714238`; local uncommitted Part 4 work. Archived source rules are evaluated as saved documents, not asserted as current policy.

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

The real index is LlamaIndex `VectorStoreIndex` backed by `SimpleVectorStore`, with 925 normalized 384-dimensional MiniLM vectors. The embedding model is `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Its cache is explicit, and the experiment loads it offline. The final index took 11.601 seconds to build; this is one observation, not a benchmark.

[Chunk records](../raw/part4/scored-20260928-04/chunks.jsonl) · [Actual index audit](../raw/part4/scored-20260928-04/index_audit.json). The following genuine browser capture places the actual chunk/index code directly above its saved outputs.

![R1 code and actual corpus/index/chunk output](../screenshots/part4/scored-20260928-04/01-corpus-index-chunks.png)


## Configurations, development and provenance (R2–R3)

The small CLI remains `code/rag.py`, with local MiniLM embeddings, LlamaIndex and Ollama 0.33.0 in the separate `.venv-rag` environment. Every final A/B/C and sweep answer uses **Qwen2.5 3B**, digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`, temperature 0, seed 6102, `think:false`, a 4096-token window and a 768-token output limit. Inference runs locally on the Apple M4 with 24 GiB RAM. No paid or cloud inference was used.

| Configuration | Treatment |
| --- | --- |
| A | Question alone; no supplied corpus, labels or grounding rules. |
| B | Raw top-k dense-retrieved text in its retrieval order; main k=3. |
| C | Same raw candidates as B; question-only specificity classification; for clear questions, cosine cutoff 0.50, conservative deduplication, score ordering, source labels, token budget and explicit grounding/prose rules; for ambiguity, an evidence-free clarifying question. |

Only C adds a separate **Qwen2.5 7B specificity classifier**, digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`. It receives the question and general rules only, and returns `CLEAR` or `CLARIFY`. The 3B model then generates the actual final answer or clarification. There is no copied answer, output replacement, gold evidence injection or test-question special case. All final-answer settings remain common across A/B/C; C has eight additional model calls, so this is a system comparison rather than an isolated prompt-only experiment. C's end-to-end timing includes those calls.

The grounded prompt now explicitly requires complete answer sentences, supporting evidence numbers after factual statements, and coverage of every part of the question: a citation alone is not an answer. The exact insufficient-evidence refusal remains `I cannot answer this question from the provided documents`. C allows at most 1800 generation tokens of evidence, including metadata, plus 128 native-template margin and the 768-token answer reserve. Matching pinned 3B/7B tokenizers count their respective prompts. All actual API counts fit the reserved windows.

The earlier `[1]` failure was real: raw Ollama output matched the saved answer, `done_reason` was `stop`, and only four tokens were generated with ample remaining capacity. A separate development question about disclosure retention reproduced it. Adding a general prose requirement changed that answer into complete, correctly cited text. Repeated clarification prompt variants still failed with 3B; the 7B question-only classifier correctly separated specificity from answer availability. Using 7B for final answers was rejected because it confused a HUD complaint deadline with a private-lawsuit deadline. Dense/BM25 fusion and one local cross-encoder trial also missed that development fact and were not adopted. Dense retrieval and its original cutoff therefore remain unchanged.

The integrated pilot passed the **unchanged eight-question development gate**: two supported cited answers, exact refusals when actual context lacked the answer, and one appropriate clarification. D2/D3 abstentions pass the generation-behavior check but remain retrieval and full-corpus answer failures. D7's wording is awkward; that limitation is recorded. [Development assessment](../raw/part4/development-followup-integrated-01/gate_assessment.json) precedes the freeze at `2026-09-28T05:48:33.114621+00:00`. The eight repeatedly inspected development questions are calibration evidence, not independent accuracy measurement. [FOLLOWUP_DIAGNOSIS.md](FOLLOWUP_DIAGNOSIS.md) retains every failed probe and the bounded retrieval investigation.

The selected run reads frozen sources/questions/configuration while executing imported live code; matching start/end hashes identify that code. Requests and retrieval printouts are saved before calls. No live generation inputs changed. Scored questions and evaluation definitions are unchanged, and earlier runs remain separate. [Metadata](../raw/part4/scored-20260928-04/run_metadata.json), [requests](../raw/part4/scored-20260928-04/requests.jsonl), [retrievals](../raw/part4/scored-20260928-04/retrievals.jsonl), [auxiliary calls](../raw/part4/scored-20260928-04/routing_responses.jsonl), [transcript](../raw/part4/scored-20260928-04/RUN_LOG.txt).

![R2 code and printed retrieval before generation](../screenshots/part4/scored-20260928-04/02-retrieval-before-generation.png)

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

A separate full-corpus semantic check found that the nearby combined-inspection passage omits the requested actions, so it is not a single-chunk substitute. Q3 requires known lead information **and** available records/reports; equivalent EPA passages are alternatives within each fact group. Q4 requires clarification. Q5's property/date and Q6's sports result have no supporting corpus passage. See [questions and exact gold spans](questions.yaml), [preflight review](preflight_review.json), and the selected [coverage audit](../raw/part4/scored-20260928-04/gold_chunk_audit.json).


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
| C | 1/3 | 4/6 | 1/3 | 4/5 | 6/6 | 3/3 | 2/2 | 2/2 |

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
| Q3-C-k3 | Yes | Yes | Yes | Yes | N/A |
| Q4-A-k0 | N/A | N/A | Yes | N/A | N/A |
| Q4-B-k3 | N/A | N/A | No | No | N/A |
| Q4-C-k3 | N/A | N/A | Yes | N/A | N/A |
| Q5-A-k0 | N/A | N/A | Yes | No | Yes |
| Q5-B-k3 | N/A | N/A | Yes | No | Yes |
| Q5-C-k3 | N/A | N/A | Yes | N/A | Yes |
| Q6-A-k0 | N/A | N/A | No | No | No |
| Q6-B-k3 | N/A | N/A | No | No | No |
| Q6-C-k3 | N/A | N/A | Yes | N/A | Yes |

Q1's requested 14-day passage exists in the index but never reaches B/C. Q2 retrieves risk-assessment evidence while missing the standalone inspection definition at every tested k. Its topical distractors all pass the 0.50 cutoff. Q3 now supplies both required information groups with supporting citations. Q4 now asks for the process and jurisdiction. Q5/Q6 exact refusals remain intact. A/B answers and supplied contexts happen to be byte-identical to the previous run, but these are fresh calls with their own raw records and timings; no old output was substituted.

[Claim-level judgments](../raw/part4/scored-20260928-04/judgments.json) · [Evaluation CSV](../raw/part4/scored-20260928-04/evaluation.csv) · [A/B/C answers](../raw/part4/scored-20260928-04/comparison.csv) · [Summary CSV](../raw/part4/scored-20260928-04/evaluation_summary.csv).

![R6 evaluation code and saved summary](../screenshots/part4/scored-20260928-04/03-evaluation-summary.png)

## Context sweep (R5)

Q2 uses identical wording at k=1,3,5. B/C share candidates for each k; k=3 reuses its main answer. The four other answers are additional calls. Each of C's three sweep responses also has its own question-only classifier call, including the reused main call.

| Config/k | Reused main | Raw/kept | Evidence tokens | Prompt/output tokens | Final generation s | Auxiliary s | End-to-end s | Correct | Grounded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B/1 | No | 1/1 | 96 | 171/87 | 2.317 | 0.000 | 2.331 | No | No |
| B/3 | Yes | 3/3 | 273 | 348/116 | 3.659 | 0.000 | 3.676 | Yes | No |
| B/5 | No | 5/5 | 436 | 511/71 | 3.032 | 0.000 | 3.050 | No | No |
| C/1 | No | 1/1 | 156 | 376/60 | 1.660 | 0.513 | 2.191 | No | No |
| C/3 | Yes | 3/3 | 465 | 685/50 | 2.418 | 0.320 | 2.762 | No | No |
| C/5 | No | 5/5 | 760 | 980/50 | 3.647 | 0.120 | 3.794 | No | No |

At k=1 the risk-assessment passage is available. k=3 adds buyer inspection opportunities and a combined procedure; k=5 adds disclosure paperwork and records. The missing inspection definition never appears. No duplicate or budget drop occurs. Extra context did not fix the missing fact. B k=3 is correct against the full-corpus key but not fully supported by its actual context. C k=1 omits citations, and C k=3/5 cite passages that do not establish the standalone inspection claim. **No k wins on complete, supported, cited answering.** Single-run timings are observations, not a latency benchmark. [Six-row sweep CSV](../raw/part4/scored-20260928-04/k_sweep.csv).

## Analysis (R7; 300–500 words)
<!-- ANALYSIS_START -->
Retrieval-augmented generation finds document passages and asks a model to answer from them. This follow-up shows that retrieval and answer generation can fail independently. The correct fourteen-day rejection deadline exists in the index, but Q1's top three passages omit it. C safely refuses, which still counts as incorrect for an answerable question. Q2 retrieves the risk-assessment definition but misses the standalone paint-inspection definition at every tested k.

The earlier Q3 failure was different. C received sufficient evidence but returned only “[1]” and stopped normally. A development question reproduced the same behavior. Explicitly requiring complete answer sentences and supporting citations repaired that development answer without adding facts. In the frozen rerun, Q3 states that renters should receive known lead information and available records and reports, with supporting citations. This meets our plan's completion criterion; the assignment does not explicitly set that minimum.

Clarification needed a separate improvement. Prompt changes alone did not reliably distinguish an ambiguous question from a clear question whose answer was unavailable. A local 7B model now classifies question specificity without seeing evidence, while the same 3B model generates every final A/B/C answer. C asks which process and jurisdiction Q4 concerns. It still refuses Q5's unavailable rent and Q6's unrelated sports result exactly. A and B answer Q6 from memory, violating the intended refusal behavior. C's additional eight classifier calls are recorded and included in its total latency.

Increasing context did not solve Q2. k=3 adds passages about inspection opportunities and a combined procedure; k=5 adds disclosure paperwork. These passages are topical but insufficient. B at k=3 gives the expected distinction without full supplied support. C's inspection claim remains incomplete or unsupported, and its k=1 answer omits citations. No k produces a complete, supported, cited answer. Development trials of keyword fusion and a passage reranker also missed a different deadline fact, so they were not adopted.

The fixed 500-character chunks and 50-character overlap avoid embedding truncation while splitting related concepts across passages. Source metadata makes citations traceable, but a valid number does not guarantee support. Ordering and chunk size were not varied. C removes six low-scoring candidates for Q5/Q6 and withholds three candidates while clarifying Q4; no duplicate or budget removals occur.

Main accuracy is A 2/6, B 3/6 and C 4/6. These six questions and repeatedly inspected development examples cannot establish general reliability. Automated checks verify files, exact strings, provenance and accounting; assistant semantic review judges completeness and support. The remaining Q1/Q2 errors are retained, and student review remains necessary.
<!-- ANALYSIS_END -->

## Verification and limitations (R8)

Focused tests: **65 passed**; [saved test output](../raw/part4/followup-setup-20260928/tests-focused-final.txt). Tests cover corpus allowlisting, character/token boundaries, deduplication, prompt isolation, separate routing/final model roles, failure persistence, evaluation denominators, citations, exact refusals, hash integrity, model/token mismatch rejection and development-before-freeze provenance. Nine tests exercise the rejected optional fusion helper; that method is not used in the selected run. The implementation compiles. Tests use synthetic fixtures and do not establish model answer quality.

All **22 final and eight auxiliary calls** stopped normally, without transport errors or overflow. The [Part 4 verification receipt](verification.json) separately identifies automated evidence-consistency checks and the plan criterion assessed from saved semantic judgments. The [handoff](HANDOFF.md) records exact reproduction commands, cache paths and remaining work. All historical runs/screenshots, Parts 1–3 code/evidence and databases were preserved; the old benchmark was not rerun. No commit, push, publication, tag or combined homework PDF was produced.

## Genuine captures and unedited answers (R3–R5, R8)

The 25 PNGs are real Chromium screenshots of saved local records, explicitly labeled as saved-output browser views. They are not live terminal captures. Frozen code appears with the corresponding raw prompt/output; C views also show the actual auxiliary prompt and decision. Exact-text and overflow checks accompany a separate representative visual review. [Capture manifest](../screenshots/part4/scored-20260928-04/manifest.json) · [Visual review](../screenshots/part4/scored-20260928-04/visual_review.json) · [Method](SCREENSHOT_METHOD.md). Long images require readable placement or splitting during later PDF assembly.

### Q1-A-k0 — main

According to the archived HUD tenant-selection handbook, how many days does an applicant have to request a meeting to dispute a rejection?

Correct: **No**; grounded: **No**. Does not provide the archived 14-day deadline; instead declines access and suggests where to look.

Unedited model output:

```text
I'm sorry, but I don't have direct access to an archived HUD tenant-selection handbook or any specific document to provide you with the exact information you're looking for. The handbook or any relevant document might contain this information, but without direct access to it, I can't provide the specific number of days.

Typically, such information is found in the terms and conditions or the dispute resolution process section of the handbook. If you have the handbook or can access it, you should be able to find this information within the dispute resolution or appeal process section.

If you need this information urgently, I recommend checking the handbook or contacting the relevant authority or department for the most accurate and up-to-date information.
```

![Actual code, prompt and output for Q1-A-k0](../screenshots/part4/scored-20260928-04/Q1-A-k0.png)

### Q1-B-k3 — main

According to the archived HUD tenant-selection handbook, how many days does an applicant have to request a meeting to dispute a rejection?

Correct: **No**; grounded: **No**. Abstains because retrieval missed the deadline; this remains incorrect for the answerable corpus question.

Unedited model output:

```text
The provided text does not contain information about how many days an applicant has to request a meeting to dispute a rejection. The text discusses tenant selection plans, reconsideration of previously denied applicants, and retention of forms, but does not specify a timeframe for disputing a rejection.
```

![Actual code, prompt and output for Q1-B-k3](../screenshots/part4/scored-20260928-04/Q1-B-k3.png)

### Q1-C-k3 — main

According to the archived HUD tenant-selection handbook, how many days does an applicant have to request a meeting to dispute a rejection?

Correct: **No**; grounded: **N/A**. Exact refusal is cautious with the missing context but omits the corpus-answerable 14-day fact.

Unedited model output:

```text
I cannot answer this question from the provided documents
```

![Actual code, prompt and output for Q1-C-k3](../screenshots/part4/scored-20260928-04/Q1-C-k3.png)

### Q2-A-k0 — main

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct: **No**; grounded: **No**. Does not reliably preserve the inspection/risk-assessment distinction: it assigns deteriorated-paint and dust/soil hazard checks to an inspection, alongside unsupported expanded procedures. No source citation is available.

Unedited model output:

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

![Actual code, prompt and output for Q2-A-k0](../screenshots/part4/scored-20260928-04/Q2-A-k0.png)

### Q2-B-k3 — main

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct: **Yes**; grounded: **No**. States both required full-corpus concepts: lead-paint presence/location and risk hazards/actions. Correctness against the key is distinct from actual-context support.

Unedited model output:

```text
According to the EPA pamphlet, a lead-based paint inspection typically locates areas in a home that have lead-based paint, while a risk assessment identifies any lead hazards present, such as from paint, dust, or soil, and what actions are needed to address these hazards.

Specifically:
- A lead-based paint inspection can locate areas with lead-based paint, such as doors, windows, floors, stairs, and walls.
- A risk assessment identifies any lead hazards, including from dust near painted surfaces and bare soil in the yard, and provides recommendations for addressing these hazards.
```

![Actual code, prompt and output for Q2-B-k3](../screenshots/part4/scored-20260928-04/Q2-B-k3.png)

### Q2-C-k3 — main

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct: **No**; grounded: **No**. Gives inspection presence but omits where lead-based paint is located. The complete requested distinction is therefore missing.

Unedited model output:

```text
A lead-based paint inspection locates if your home has any lead-based paint, and a risk assessment identifies if your home currently has any lead hazards from paint, dust or soil, and what actions to take to address any hazards. [1]
```

![Actual code, prompt and output for Q2-C-k3](../screenshots/part4/scored-20260928-04/Q2-C-k3.png)

### Q3-A-k0 — main

According to the supplied documents, what information about known lead-based paint hazards should a prospective renter of covered pre-1978 housing receive before signing a lease?

Correct: **No**; grounded: **No**. Does not clearly require all available records/reports and adds a supposed standardized LP-HIN form and broad procedural duties not established by the frozen key. It is not a complete accurate source-based answer.

Unedited model output:

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

![Actual code, prompt and output for Q3-A-k0](../screenshots/part4/scored-20260928-04/Q3-A-k0.png)

### Q3-B-k3 — main

According to the supplied documents, what information about known lead-based paint hazards should a prospective renter of covered pre-1978 housing receive before signing a lease?

Correct: **Yes**; grounded: **No**. Correctly includes known lead information and all available records/reports, with none-known alternatives, for covered renters; the warning statement is also supported.

Unedited model output:

```text
According to the supplied documents, a prospective renter of covered pre-1978 housing should receive information about known lead-based paint hazards. Specifically, the renter should receive a disclosure of known information about the presence of lead-based paint or lead-based paint hazards, or be informed that there are none. They should also receive all available records and reports on lead-based paint and lead-based paint hazards, or be informed that there are none. Additionally, a specific warning statement about lead-based paint should be included.
```

![Actual code, prompt and output for Q3-B-k3](../screenshots/part4/scored-20260928-04/Q3-B-k3.png)

### Q3-C-k3 — main

According to the supplied documents, what information about known lead-based paint hazards should a prospective renter of covered pre-1978 housing receive before signing a lease?

Correct: **Yes**; grounded: **Yes**. Completely states both essential obligations for covered renters before signing the lease, with the responsible parties and supporting citations [1] and [3].

Unedited model output:

```text
According to the supplied documents, a prospective renter of covered pre-1978 housing should receive the information about known information about the presence of lead-based paint or lead-based paint hazards, as well as all available records and reports on lead-based paint and lead-based paint hazards, from the sellers, landlords, agents, and rental property managers before signing a lease. [1], [3]
```

![Actual code, prompt and output for Q3-C-k3](../screenshots/part4/scored-20260928-04/Q3-C-k3.png)

### Q4-A-k0 — main

How long do I have to file?

Correct: **Yes**; grounded: **N/A**. Asks what filing means and offers possible categories as questions, without choosing a deadline.

Unedited model output:

```text
The term "file" can refer to different things depending on the context. Could you please specify what you mean by "file"? Are you referring to filing a legal case, submitting an academic assignment, or something else? Providing more context will help me give you a more accurate and helpful response.
```

![Actual code, prompt and output for Q4-A-k0](../screenshots/part4/scored-20260928-04/Q4-A-k0.png)

### Q4-B-k3 — main

How long do I have to file?

Correct: **No**; grounded: **No**. Declines to determine a duration instead of asking which process the user means.

Unedited model output:

```text
Based on the information provided in the text, the duration for filing is not explicitly stated. The text discusses various aspects of tenant files, confidentiality, and retention periods for documents, but does not specify a filing deadline. Therefore, I cannot answer "How long do I have to file?" with the given information.
```

![Actual code, prompt and output for Q4-B-k3](../screenshots/part4/scored-20260928-04/Q4-B-k3.png)

### Q4-C-k3 — main

How long do I have to file?

Correct: **Yes**; grounded: **N/A**. Asks which legal or administrative process and jurisdiction are intended; it selects no particular filing action or deadline.

Unedited model output:

```text
What type of legal or administrative process are you referring to, and in which jurisdiction?
```

![Actual code, prompt and output for Q4-C-k3](../screenshots/part4/scored-20260928-04/Q4-C-k3.png)

### Q5-A-k0 — main

What is the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026?

Correct: **Yes**; grounded: **No**. Declines to supply an unknown rent and suggests contacting the property.

Unedited model output:

```text
I don't have real-time data access or the ability to search for specific properties like Cedar Grove Apartments. To find the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026, you would need to contact the property directly or visit their official website or contact their leasing office. They would have the most accurate and up-to-date information regarding their rental rates and availability.
```

![Actual code, prompt and output for Q5-A-k0](../screenshots/part4/scored-20260928-04/Q5-A-k0.png)

### Q5-B-k3 — main

What is the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026?

Correct: **Yes**; grounded: **No**. Correctly declines the absent property/date-specific rent instead of inventing a price.

Unedited model output:

```text
I do not have enough information in the provided text to determine the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026. The text does not contain any details about Cedar Grove Apartments or Unit 4B. It discusses various housing subsidy and rent-related topics, but does not provide specific information about this particular property or date.
```

![Actual code, prompt and output for Q5-B-k3](../screenshots/part4/scored-20260928-04/Q5-B-k3.png)

### Q5-C-k3 — main

What is the monthly rent for Unit 4B at Cedar Grove Apartments on September 27, 2026?

Correct: **Yes**; grounded: **N/A**. Uses the exact refusal for rent information absent from the corpus.

Unedited model output:

```text
I cannot answer this question from the provided documents
```

![Actual code, prompt and output for Q5-C-k3](../screenshots/part4/scored-20260928-04/Q5-C-k3.png)

### Q6-A-k0 — main

Who won the 2022 FIFA World Cup?

Correct: **No**; grounded: **No**. Answers the World Cup question from memory instead of refusing; recalled sports information fails the required corpus-only behavior.

Unedited model output:

```text
The 2022 FIFA World Cup was won by Argentina. They defeated France in the final match with a score of 3-0. This victory marked Argentina's third World Cup title, following their wins in 1978 and 1986.
```

![Actual code, prompt and output for Q6-A-k0](../screenshots/part4/scored-20260928-04/Q6-A-k0.png)

### Q6-B-k3 — main

Who won the 2022 FIFA World Cup?

Correct: **No**; grounded: **No**. Despite acknowledging missing sports evidence, ultimately answers Argentina. That is not a semantic refusal.

Unedited model output:

```text
The provided text does not contain information about who won the 2022 FIFA World Cup. The text discusses various financial and legal scenarios related to assets, income, and trusts. To answer the question about the 2022 FIFA World Cup winner, I would need to look up current sports news, which I do not have access to. Based on current knowledge, the winner of the 2022 FIFA World Cup was Argentina.
```

![Actual code, prompt and output for Q6-B-k3](../screenshots/part4/scored-20260928-04/Q6-B-k3.png)

### Q6-C-k3 — main

Who won the 2022 FIFA World Cup?

Correct: **Yes**; grounded: **N/A**. Uses the exact refusal for the unrelated sports question.

Unedited model output:

```text
I cannot answer this question from the provided documents
```

![Actual code, prompt and output for Q6-C-k3](../screenshots/part4/scored-20260928-04/Q6-C-k3.png)

### Q2-B-k1 — sweep

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct: **No**; grounded: **No**. Incorrectly describes an inspection as locating lead hazards and assigns risk-assessor sampling details to it.

Unedited model output:

```text
According to the EPA pamphlet, a lead-based paint inspection locates any lead hazards in a home, specifically focusing on deteriorated paint on doors, windows, floors, stairs, and walls. On the other hand, a risk assessment identifies any lead hazards in a home, including those from dust near painted surfaces and bare soil in the yard. A risk assessment also identifies what actions need to be taken to address any identified hazards.
```

![Actual code, prompt and output for Q2-B-k1](../screenshots/part4/scored-20260928-04/Q2-B-k1.png)

### Q2-C-k1 — sweep

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct: **No**; grounded: **No**. Assigns the risk-assessor deteriorated-paint sampling task to an inspection and omits the correct paint-presence/location definition.

Unedited model output:

```text
According to the EPA pamphlet, a lead-based paint inspection locates deteriorated paint on doors, windows, floors, stairs, and walls. A risk assessment identifies if the home currently has any lead hazards from paint, dust, or soil, and what actions to take to address any hazards.
```

![Actual code, prompt and output for Q2-C-k1](../screenshots/part4/scored-20260928-04/Q2-C-k1.png)

### Q2-B-k5 — sweep

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct: **No**; grounded: **No**. Conflates locating lead hazards and disclosure details with the standalone inspection role; the required distinction is incorrect.

Unedited model output:

```text
According to the EPA pamphlet, a lead-based paint inspection typically locates lead-based paint hazards in the home or building, including the location of the lead-based paint and the condition of the painted surfaces. On the other hand, a risk assessment identifies any lead hazards in the home or building and what actions need to be taken to address these hazards.
```

![Actual code, prompt and output for Q2-B-k5](../screenshots/part4/scored-20260928-04/Q2-B-k5.png)

### Q2-C-k5 — sweep

According to the EPA pamphlet, what does a lead-based paint inspection locate, and what does a risk assessment identify about hazards and actions to take?

Correct: **No**; grounded: **No**. Gives inspection presence but omits paint location, so the requested complete distinction is still missing.

Unedited model output:

```text
A lead-based paint inspection tells you if your home has any lead-based paint, and a risk assessment identifies if your home currently has any lead hazards from paint, dust or soil, and what actions to take to address any hazards. [3]
```

![Actual code, prompt and output for Q2-C-k5](../screenshots/part4/scored-20260928-04/Q2-C-k5.png)

