"""Render the follow-up report from retained, manually evaluated evidence."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from src.rag.evaluation import analysis_word_count

run_id = sys.argv[1] if len(sys.argv)>1 else 'scored-20260928-04'
if run_id != 'scored-20260928-04':
    raise ValueError('This report narrative is reviewed for scored04 only; a new run needs new semantic review and prose.')
out = Path(sys.argv[2]) if len(sys.argv)>2 else ROOT/'reports/hw04/part4/REPORT_SECTION.md'
run=ROOT/'reports/hw04/raw/part4'/run_id
read=lambda p:json.loads(p.read_text())
rows=[json.loads(line) for line in (run/'responses.jsonl').read_text().splitlines()]
lookup={r['response_id']:r for r in rows}
judgments={j['response_id']:j for j in read(run/'judgments.json')['responses']}
summary=read(run/'summary.json')['configurations']
meta=read(run/'run_metadata.json'); audit=read(run/'index_audit.json')
captures=read(ROOT/'reports/hw04/screenshots/part4'/run_id/'manifest.json')['captures']
old=(ROOT/'reports/hw04/raw/part4/followup-setup-20260928/before/reports/hw04/part4/REPORT_SECTION.md').read_text()
corpus=old.split('## Corpus and actual index (R1)')[1].split('## Configurations, calibration and provenance')[0]
corpus=corpus.replace('21.102 seconds',f"{audit['build_seconds']:.3f} seconds").replace('scored-20260928-03',run_id)
questions=old.split('## Six frozen questions and evidence proof (R4)')[1].split('## Evaluation definitions')[0].replace('scored-20260928-03',run_id)
definitions=old.split('## Evaluation definitions and main results (R6)')[1].split('| Configuration |')[0]
yn=lambda value:'N/A' if value is None else 'Yes' if value else 'No'
raw=f'../raw/part4/{run_id}'
ss=f'../screenshots/part4/{run_id}'
parts=[f'''# Part 4 — Local retrieval-augmented generation

**The focused follow-up is complete locally.** The selected run `{run_id}` retains 18 main A/B/C answers and four additional sweep answers, plus eight auxiliary clarification decisions. All 30 local calls ended normally. C now gives a complete, supported, cited Q3 answer, clarifies Q4, and refuses Q5/Q6 exactly. A successful cited C answer is **our reviewed plan's completion criterion**, not an explicit assignment minimum. Q1/Q2 failures remain in the results.

SID4 **6102** · PORT_BASE **8702** · PREFIX **s6102** · SEED **6102** · VERIFY_SEED **266102** · DOMAIN_ID **6**. Branch `codex/hw4-part2-backend`; unchanged base HEAD `421c77ddca9ce998e5088dd305ea4da9bb714238`; local uncommitted Part 4 work. Archived source rules are evaluated as saved documents, not asserted as current policy.

## Corpus and actual index (R1)
{corpus}
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

The integrated pilot passed the **unchanged eight-question development gate**: two supported cited answers, exact refusals when actual context lacked the answer, and one appropriate clarification. D2/D3 abstentions pass the generation-behavior check but remain retrieval and full-corpus answer failures. D7's wording is awkward; that limitation is recorded. [Development assessment](../raw/part4/development-followup-integrated-01/gate_assessment.json) precedes the freeze at `{meta['config']['frozen_at']}`. The eight repeatedly inspected development questions are calibration evidence, not independent accuracy measurement. [FOLLOWUP_DIAGNOSIS.md](FOLLOWUP_DIAGNOSIS.md) retains every failed probe and the bounded retrieval investigation.

The selected run reads frozen sources/questions/configuration while executing imported live code; matching start/end hashes identify that code. Requests and retrieval printouts are saved before calls. No live generation inputs changed. Scored questions and evaluation definitions are unchanged, and earlier runs remain separate. [Metadata]({raw}/run_metadata.json), [requests]({raw}/requests.jsonl), [retrievals]({raw}/retrievals.jsonl), [auxiliary calls]({raw}/routing_responses.jsonl), [transcript]({raw}/RUN_LOG.txt).

![R2 code and printed retrieval before generation]({ss}/02-retrieval-before-generation.png)

## Six frozen questions and evidence proof (R4)
{questions}
## Evaluation definitions and main results (R6)
{definitions}
| Configuration | Retrieval Q1–Q3 | Accuracy all six | Answerable Q1–Q3 | Faithful claims | Format | Robustness Q4–Q6 | Refusal Q5/Q6 | Exact refusal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |''']
metrics=['correct_retrieval','accuracy','answerable_accuracy','faithfulness','format_compliance','robustness','required_refusal','exact_required_refusal']
for c in 'ABC':parts.append('| '+c+' | '+' | '.join(summary[c][key]['display'] for key in metrics)+' |')
parts.append('\n| Response | Correct retrieval | Final coverage | Correct answer | Grounded | Refused when needed |\n| --- | --- | --- | --- | --- | --- |')
for r in rows:
 if r['phase']=='main':
  j=judgments[r['response_id']]
  parts.append('| '+r['response_id']+' | '+' | '.join(yn(j[k]) for k in ['correct_retrieval','final_context_coverage','correct_answer','grounded','refused_when_needed'])+' |')
parts.append(f'''
Q1's requested 14-day passage exists in the index but never reaches B/C. Q2 retrieves risk-assessment evidence while missing the standalone inspection definition at every tested k. Its topical distractors all pass the 0.50 cutoff. Q3 now supplies both required information groups with supporting citations. Q4 now asks for the process and jurisdiction. Q5/Q6 exact refusals remain intact. A/B answers and supplied contexts happen to be byte-identical to the previous run, but these are fresh calls with their own raw records and timings; no old output was substituted.

[Claim-level judgments]({raw}/judgments.json) · [Evaluation CSV]({raw}/evaluation.csv) · [A/B/C answers]({raw}/comparison.csv) · [Summary CSV]({raw}/evaluation_summary.csv).

![R6 evaluation code and saved summary]({ss}/03-evaluation-summary.png)

## Context sweep (R5)

Q2 uses identical wording at k=1,3,5. B/C share candidates for each k; k=3 reuses its main answer. The four other answers are additional calls. Each of C's three sweep responses also has its own question-only classifier call, including the reused main call.

| Config/k | Reused main | Raw/kept | Evidence tokens | Prompt/output tokens | Final generation s | Auxiliary s | End-to-end s | Correct | Grounded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |''')
for ref in read(run/'sweep_references.json'):
 r=lookup[ref['response_id']]; j=judgments[r['response_id']]; api=r['raw_response']
 parts.append(f"| {r['configuration']}/{r['requested_k']} | {yn(ref['reused_main'])} | {r['returned_count']}/{r['retained_count']} | {r['evidence_token_bound']} | {api['prompt_eval_count']}/{api['eval_count']} | {r['generation_seconds']:.3f} | {r['routing_generation_seconds']:.3f} | {r['end_to_end_seconds']:.3f} | {yn(j['correct_answer'])} | {yn(j['grounded'])} |")
parts.append(f'''
At k=1 the risk-assessment passage is available. k=3 adds buyer inspection opportunities and a combined procedure; k=5 adds disclosure paperwork and records. The missing inspection definition never appears. No duplicate or budget drop occurs. Extra context did not fix the missing fact. B k=3 is correct against the full-corpus key but not fully supported by its actual context. C k=1 omits citations, and C k=3/5 cite passages that do not establish the standalone inspection claim. **No k wins on complete, supported, cited answering.** Single-run timings are observations, not a latency benchmark. [Six-row sweep CSV]({raw}/k_sweep.csv).

## Analysis (R7; 300–500 words)
<!-- ANALYSIS_START -->
Retrieval-augmented generation finds document passages and asks a model to answer from them. This follow-up shows that retrieval and answer generation can fail independently. The correct fourteen-day rejection deadline exists in the index, but Q1's top three passages omit it. C safely refuses, which still counts as incorrect for an answerable question. Q2 retrieves the risk-assessment definition but misses the standalone paint-inspection definition at every tested k.

The earlier Q3 failure was different. C received sufficient evidence but returned only “[1]” and stopped normally. A development question reproduced the same behavior. Explicitly requiring complete answer sentences and supporting citations repaired that development answer without adding facts. In the frozen rerun, Q3 states that renters should receive known lead information and available records and reports, with supporting citations. This meets our plan's completion criterion; the assignment does not explicitly set that minimum.

Clarification needed a separate improvement. Prompt changes alone did not reliably distinguish an ambiguous question from a clear question whose answer was unavailable. A local 7B model now classifies question specificity without seeing evidence, while the same 3B model generates every final A/B/C answer. C asks which process and jurisdiction Q4 concerns. It still refuses Q5's unavailable rent and Q6's unrelated sports result exactly. A and B answer Q6 from memory, violating the intended refusal behavior. C's additional eight classifier calls are recorded and included in its total latency.

Increasing context did not solve Q2. k=3 adds passages about inspection opportunities and a combined procedure; k=5 adds disclosure paperwork. These passages are topical but insufficient. B at k=3 gives the expected distinction without full supplied support. C's inspection claim remains incomplete or unsupported, and its k=1 answer omits citations. No k produces a complete, supported, cited answer. Development trials of keyword fusion and a passage reranker also missed a different deadline fact, so they were not adopted.

The fixed 500-character chunks and 50-character overlap avoid embedding truncation while splitting related concepts across passages. Source metadata makes citations traceable, but a valid number does not guarantee support. Ordering and chunk size were not varied. C removes six low-scoring candidates for Q5/Q6 and withholds three candidates while clarifying Q4; no duplicate or budget removals occur.

Main accuracy is A {summary['A']['accuracy']['display']}, B {summary['B']['accuracy']['display']} and C {summary['C']['accuracy']['display']}. These six questions and repeatedly inspected development examples cannot establish general reliability. Automated checks verify files, exact strings, provenance and accounting; assistant semantic review judges completeness and support. The remaining Q1/Q2 errors are retained, and student review remains necessary.
<!-- ANALYSIS_END -->

## Verification and limitations (R8)

Historical pre-cleanup tests: **65 passed**; [saved output](../raw/part4/followup-setup-20260928/tests-focused-final.txt). Nine of those tests covered the rejected fusion helper, which is now preserved with its tests in the [historical archive](archive/rejected-hybrid-20260928/README.md) and removed from live code. **Post-cleanup: 56 remaining tests passed**; [separate output](../raw/part4/cleanup-hybrid-20260928-01/tests.txt). The retained tests cover corpus allowlisting, character/token boundaries, deduplication, prompt isolation, separate routing/final model roles, failure persistence, evaluation denominators, citations, exact refusals, hash integrity, model/token mismatch rejection and development-before-freeze provenance. Python compilation and capture-script syntax checks pass. Tests use synthetic fixtures and do not establish model answer quality. The cleanup does not change the selected configuration, scored answers, judgments, screenshots or analysis; [offline checks](../raw/part4/cleanup-hybrid-20260928-01/checks.json) and a [fresh selected-evidence receipt](../raw/part4/cleanup-hybrid-20260928-01/verification-selected.json) document preservation.

All **22 final and eight auxiliary calls** stopped normally, without transport errors or overflow. The [Part 4 verification receipt](verification.json) separately identifies automated evidence-consistency checks and the plan criterion assessed from saved semantic judgments. The [handoff](HANDOFF.md) records exact reproduction commands, cache paths and remaining work. All historical runs/screenshots, Parts 1–3 code/evidence and databases were preserved; the old benchmark was not rerun. No commit, push, publication, tag or combined homework PDF was produced.

## Genuine captures and unedited answers (R3–R5, R8)

The 25 PNGs are real Chromium screenshots of saved local records, explicitly labeled as saved-output browser views. They are not live terminal captures. Frozen code appears with the corresponding raw prompt/output; C views also show the actual auxiliary prompt and decision. Exact-text and overflow checks accompany a separate representative visual review. [Capture manifest]({ss}/manifest.json) · [Visual review]({ss}/visual_review.json) · [Method](SCREENSHOT_METHOD.md). Long images require readable placement or splitting during later PDF assembly.
''')
for r in rows:
 j=judgments[r['response_id']]
 capture=next(c for c in captures if r['response_id'] in c.get('response_ids',[]))
 filename=capture['path']
 if not filename:
  raise ValueError(f'Capture filename missing: {capture.keys()}')
 parts.append(f"### {r['response_id']} — {r['phase']}\n\n{r['question']}\n\nCorrect: **{yn(j['correct_answer'])}**; grounded: **{yn(j['grounded'])}**. {j['reasons']['answer']}\n\nUnedited model output:\n\n```text\n{r['answer']}\n```\n\n![Actual code, prompt and output for {r['response_id']}]({ss}/{Path(filename).name})\n")
text='\n'.join(parts)+'\n'
assert 300<=analysis_word_count(text)<=500
out.write_text(text)
print(json.dumps({'report':str(out),'analysis_words':analysis_word_count(text),'run':run_id}))
