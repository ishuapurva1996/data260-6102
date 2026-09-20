# Pre-retrieval gold evidence audit

Prepared by the Codex corpus agent on September 20, 2026 UTC through source reading, full-corpus lexical searches and visual inspection of the five relevant original PDF pages. This records agent work, not independent student work. No model embeddings, vector index, query engine or graded retrieval runs were used during this audit.

The corpus is limited to the four `sources[].path` text files in `CORPUS_MANIFEST.json`; each is one source document. HUD’s separately published handbook chapters are separate corpus documents. Gold answers refer to the archived documents, which include historical HUD material; they do not assert that historical dollar amounts remain current.

| Question | Correct answer and source | Why the evidence answers the question | Qualification that matters |
|---|---|---|---|
| Q1 | Within 14 days; `HUD_SELECTION`, paragraph 4-9.C.2.b, PDF page 28 | The rejection notice must state the applicant’s right to respond in writing or request a meeting within 14 days. | The nearby five-business-day rule is the owner’s later final decision deadline. The applicant rule says “14 days,” without “business.” |
| Q2 | $480 per eligible dependent; `HUD_INCOME`, paragraphs 5-9.A and 5-10.A.1, PDF page 41 | Paragraph 5-9 defines the deductions as subtractions from annual income; 5-10 gives the dependent deduction amount. | The question explicitly asks about the archived handbook. Eligibility exceptions are not overwritten, and this is not a current-rule claim. |
| Q3 | Boiling does not remove lead; use only cold water for drinking, cooking and baby formula; `EPA_LEAD`, PDF page 15 / printed page 13 | The two sentences in the lead-in-drinking-water section explicitly provide both parts of the answer. | A hit about lead paint, lead testing or generic water safety without these facts is insufficient. |
| Q4 | One year after discrimination occurred or ended; `HUD_FAIR`, PDF page 10 / printed page 6 | The booklet explicitly states the time limit for a complaint to HUD. | A private civil lawsuit has a different two-year period elsewhere in the booklet. That is not the asked-for process. |
| Q5 | At least 40%; `HUD_SELECTION`, paragraph 4-5.A, PDF page 10 | The rule states “not less than 40%” of assisted dwelling units becoming available during a project fiscal year. | The denominator is the assisted units that become available during that year, not 40% of all units or all household income. |

All quotations are stored verbatim in `questions.yaml` and were programmatically checked as exact substrings of their expected source text. Five source-page PNGs in `corpus/audit_previews/` were visually inspected; the numbers, wording and qualifications matched the PDFs.

## Single-source checks

“Single-source” means the requested fact is present in exactly one of the four counted documents. It does not mean that related topics cannot appear elsewhere. The complete corpus was searched using broad case-insensitive patterns, followed by direct reading of all cross-source matches. `corpus/single_source_audit.json` preserves patterns, matching line counts and locations for every question/source pair.

- **Q1:** `reject|denial|appeal|hearing|14 days|fourteen`. Other documents mention discrimination hearings or rejection in general, but none states the applicant rejection-meeting 14-day rule. The different 14-business-day VAWA documentation rule is in the same handbook chapter and is not the gold answer.
- **Q2:** `dependent|\$480|deduct|adjusted income`. Only the income chapter contains the dependent deduction or amount. The tenant-selection chapter’s matches are unrelated uses of “dependent” or “independent.”
- **Q3:** `boil|cold water|drinking water|plumbing`. Every match is in the EPA pamphlet. Neither requested fact occurs in another counted document.
- **Q4:** `complaint|one year|365|12 months`. The tenant-selection chapter refers complaints to HUD but has no filing limit. Other year/month matches concern waiting time, income calculations or infant age; only the HUD booklet states the complaint deadline.
- **Q5:** `extremely low|income.target|40%|forty`. Only the tenant-selection chapter contains the percentage rule. The income chapter merely lists “extremely low-income family” as a key term.

All five facts meet the source-uniqueness check; Q2 and Q3 are particularly clear cases because no other source discusses their requested fact. This exceeds the minimum of two single-source questions.

## Extraction audit

- Cleaned text totals 345,859 bytes across four distinct documents; no synthetic filler, duplicate document or warm-up text is counted.
- Source covers, contents, blank notes, repeated page headers/footers and contact-directory pages are excluded as specified in `SOURCES.md` and the extraction script.
- Exact repeated paragraphs longer than 100 characters are removed within each document; the page map records one removed paragraph in each handbook chapter.
- UTF-8 size and SHA-256 are recorded for each text snapshot and its original PDF. Only manifest-listed text is eligible for indexing.
- Page-map spans cover the selected substantive pages and tie each gold passage back to the original page. The table extraction limitation is disclosed; no gold passage relies on reading a flattened table.

The execution owner will make the distinct input-freeze commit containing `questions.yaml`, the corpus, the manifest and the actual experiment configuration. This audit must precede graded retrieval. Later relevance annotations must evaluate returned text independently; a source hit or high similarity score alone does not establish that the answer was retrieved.
