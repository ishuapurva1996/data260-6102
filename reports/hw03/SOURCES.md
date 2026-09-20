# Part 2 corpus sources

The graded corpus consists of four distinct official federal housing documents. Only the four text paths in `CORPUS_MANIFEST.json` are indexed. The cleaned snapshots total **345,859 UTF-8 bytes** (about 337.75 KiB), exceeding both the 250,000-byte target and the 204,800-byte hard minimum. Original PDFs, preview images and audit files are not counted.

The corpus supports rental-search questions about screening, affordability, housing discrimination and an older apartment’s lead hazards. It is a policy-and-renter-information corpus for the Rental Housing Listings domain, rather than a collection of live advertised properties. The HUD handbook and fair-housing booklet are historical snapshots; conclusions in this experiment concern retrieval of those snapshots, not whether every rule is current in 2026.

| Source ID | Document | Cleaned bytes | Text snapshot |
|---|---|---:|---|
| HUD_SELECTION | [HUD Handbook 4350.3 REV-1, Chapter 4: Waiting List and Tenant Selection](https://www.hud.gov/sites/documents/43503c4hsgh.pdf) | 145,418 | [hud_tenant_selection.txt](corpus/text/hud_tenant_selection.txt) |
| HUD_INCOME | [HUD Handbook 4350.3 REV-1, Chapter 5: Determining Income and Calculating Rent](https://www.hud.gov/sites/documents/43503c5hsgh.pdf) | 160,419 | [hud_income_rent.txt](corpus/text/hud_income_rent.txt) |
| EPA_LEAD | [Protect Your Family From Lead in Your Home](https://www.epa.gov/system/files/documents/2026-02/protectyourfamily_pamphlet_2026_3.pdf) | 21,608 | [epa_lead_2026.txt](corpus/text/epa_lead_2026.txt) |
| HUD_FAIR | [Fair Housing: Equal Opportunity for All](https://www.hud.gov/sites/documents/fheo_booklet_eng.pdf) | 18,414 | [hud_fair_housing.txt](corpus/text/hud_fair_housing.txt) |

## Provenance and hashes

All source PDFs were downloaded on September 20, 2026 UTC. Per-file completion times are recorded as `accessed_at`. SHA-256 hashes below describe the frozen local bytes, not an assumption that an upstream URL will remain unchanged.

### HUD_SELECTION

- Source URL: [HUD Handbook 4350.3 REV-1, Chapter 4: Waiting List and Tenant Selection](https://www.hud.gov/sites/documents/43503c4hsgh.pdf)
- Accessed: `2026-09-20T08:24:34.666769Z`
- Version: Archived 2013 PDF; pages contain 2007, 2009 and 2013 revision dates.
- Text file: `reports/hw03/corpus/text/hud_tenant_selection.txt`
- UTF-8 text bytes: `145418`
- Text SHA-256: `970dfc1f3a5587184b737e1019bea26eaacc42d84ff12e05a387b8c34c2d3fa1`
- Original: `reports/hw03/corpus/originals/hud_tenant_selection.pdf` (478,205 bytes)
- Original SHA-256: `103c44a4e41f855a6d1bed1b976749e77dbb0d53ebeb4fc3db119c76a015f3ef`
- Extraction: PDF pages 1–67; repeated headers/footers removed; one repeated substantive paragraph removed. Poppler pdftotext 26.04.0 -layout; NFKC normalization, line wrapping joined, PDF bullets normalized. Tables remain flattened in reading order; originals are authoritative for table layout.
- Rights: Official HUD federal publication; HUD public-domain policy covers written materials created for its website. No third-party copyright notice identified in the counted text. US public domain.

### HUD_INCOME

- Source URL: [HUD Handbook 4350.3 REV-1, Chapter 5: Determining Income and Calculating Rent](https://www.hud.gov/sites/documents/43503c5hsgh.pdf)
- Accessed: `2026-09-20T08:24:45.453746Z`
- Version: Archived 2013 PDF; pages contain 2007, 2009 and 2013 revision dates.
- Text file: `reports/hw03/corpus/text/hud_income_rent.txt`
- UTF-8 text bytes: `160419`
- Text SHA-256: `2efa6b7ef8ad15a2336b38929741b87e97ea25a996e8fed585e3cc3628612f5b`
- Original: `reports/hw03/corpus/originals/hud_income_rent.pdf` (593,676 bytes)
- Original SHA-256: `99ad54fc26c25eb56e436ec7c0a26c4a588190acc6262c823d67df209dde96fb`
- Extraction: PDF pages 1–81; repeated headers/footers removed; one repeated substantive paragraph removed. Poppler pdftotext 26.04.0 -layout; NFKC normalization, line wrapping joined, PDF bullets normalized. Tables remain flattened in reading order; originals are authoritative for table layout.
- Rights: Official HUD federal publication; HUD public-domain policy covers written materials created for its website. No third-party copyright notice identified in the counted text. US public domain.

### EPA_LEAD

- Source URL: [Protect Your Family From Lead in Your Home](https://www.epa.gov/system/files/documents/2026-02/protectyourfamily_pamphlet_2026_3.pdf)
- Accessed: `2026-09-20T08:24:44.727609Z`
- Version: January 2026; federal authors EPA, CPSC and HUD.
- Text file: `reports/hw03/corpus/text/epa_lead_2026.txt`
- UTF-8 text bytes: `21608`
- Text SHA-256: `3830114fcc78a08e1624b394b68b1a6ae42b3376e9b9a8d41707db68e50d4cad`
- Original: `reports/hw03/corpus/originals/epa_lead_2026.pdf` (1,403,637 bytes)
- Original SHA-256: `a094896c4c29df8f5b7f064bef8108346f476d3fcbbca8ae950d8e9629fb0ef8`
- Extraction: PDF pages 2–16 only; cover, contact directories and repeated back-cover summary excluded; isolated page numbers removed. Poppler pdftotext 26.04.0 -layout; NFKC normalization, line wrapping joined, PDF bullets normalized. Tables remain flattened in reading order; originals are authoritative for table layout.
- Rights: Official joint EPA/CPSC/HUD federal educational text. EPA permits noncommercial scientific and educational distribution; no third-party copyright notice identified in the counted text. Original PDF retained for educational audit; no claim is made about unrestricted commercial reuse of its photographs.

### HUD_FAIR

- Source URL: [Fair Housing: Equal Opportunity for All](https://www.hud.gov/sites/documents/fheo_booklet_eng.pdf)
- Accessed: `2026-09-20T08:24:50.950871Z`
- Version: Archived booklet; PDF metadata creation/modification June 6, 2011; publication date not asserted.
- Text file: `reports/hw03/corpus/text/hud_fair_housing.txt`
- UTF-8 text bytes: `18414`
- Text SHA-256: `c47c156c57eaaf0b84fb278f5096053548b90ff0cad5ff426c64190b51be7f5e`
- Original: `reports/hw03/corpus/originals/hud_fair_housing.pdf` (5,468,378 bytes)
- Original SHA-256: `03467e13022a3a2b3a0c99b2def6b419949bc93cbdca0d5f3e91077168c16fd2`
- Extraction: PDF pages 5–10 and 14–19 only; cover, contents, introduction, blank notes and regional contact directory excluded; partial directory text on pages 10 and 14 removed; repeated heading/footer removed. Poppler pdftotext 26.04.0 -layout; NFKC normalization, line wrapping joined, PDF bullets normalized. Tables remain flattened in reading order; originals are authoritative for table layout.
- Rights: Official HUD federal publication; HUD public-domain policy covers written materials created for its website. No third-party copyright notice identified in the counted text. US public domain.

## Rights and source selection

HUD’s [Web Publication Standards, Copyrights and Attribution](https://www.hud.gov/sites/documents/webpubstandards.pdf) state that material written or created for its websites is generally public domain, with third-party copyrights identified where applicable. The two handbook chapters and HUD booklet are official federal publications; no third-party copyright notice was identified in their extracted text. These three HUD text files alone total **324,251 bytes**, above the corpus target.

The EPA pamphlet names EPA, CPSC and HUD as authors. EPA’s [copyright-status policy](https://www.epa.gov/web-policies-and-procedures/epa-disclaimers) permits noncommercial, scientific and educational distribution and notes that individual documents may have separate terms. The corpus uses its federal educational text, with the original PDF retained for this educational audit. Photographs are not separate reusable corpus assets, and no unrestricted commercial-image license is asserted.

Authoritative landing pages: [HUD Handbook 4350.3](https://www.hud.gov/hudclips/handbooks/housing-4350-3) and [EPA Protect Your Family](https://www.epa.gov/lead/protect-your-family-lead-your-home-english). The EPA page identifies the January 2026 edition.

## Extraction and integrity checks

The reproducible extraction script is `corpus/extract_corpus.py`. It runs Poppler `pdftotext -layout` 26.04.0 against the archived PDFs, selects the substantive pages listed above, strips repeated page furniture, normalizes Unicode and whitespace, joins soft line wraps, and removes exact repeated paragraphs longer than 100 characters within a document. Two substantive duplicate paragraphs were removed in total. It does not add generated content or pad the corpus.

Run from the repository root:

```bash
python3 reports/hw03/corpus/extract_corpus.py
```

`corpus/page_map.json` maps cleaned character spans to one-based PDF page numbers. Layout extraction flattens tables and may interleave labels around diagrams; the source PDFs remain authoritative for those layouts. The five gold-answer passages are prose or explicit rules and were checked against rendered original pages, so their numbers and qualifications do not depend on a flattened table.

The original gold-evidence pages are rendered in `corpus/audit_previews/`; these are source-page inspection images, not retrieval-output screenshots. `corpus/single_source_audit.json` records full-corpus lexical checks. Their interpretation is documented in `part2/GOLD_EVIDENCE_AUDIT.md`.

The question authoring used source reading and literal text searches only. No corpus embeddings, indexes, similarity scores or graded retrieval results were used to select these five questions. The execution owner must commit the corpus, questions and actual experiment configuration before the first graded run.
