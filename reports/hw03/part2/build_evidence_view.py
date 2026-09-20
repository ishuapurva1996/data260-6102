"""Render actual saved stdout/raw evidence into browser pages for screenshots.

This does not draw screenshots or simulate a terminal. Capture the generated
HTML pages in a real browser; headers explicitly identify saved run output.
"""
from pathlib import Path
import html
import json

ROOT=Path(__file__).resolve().parents[3]
RUN=ROOT/'reports/hw03/raw/part2/baseline-20260920'
OUT=ROOT/'reports/hw03/part2/evidence_view'
CSS='''*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#162332;font:18px/1.5 system-ui,sans-serif;padding:38px 48px}h1{margin:0 0 5px;font-size:29px}h2{font-size:20px;margin:24px 0 10px}.subtitle{color:#526270;font-size:15px;margin-bottom:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;border:1px solid #ccd4dc;border-radius:8px;padding:20px;font:15px/1.5 ui-monospace,Menlo,monospace;margin:8px 0}table{border-collapse:collapse;width:100%;background:white;font-size:16px}th,td{padding:11px;border:1px solid #ccd4dc;text-align:left}th{background:#e9eff4}.note{background:#e7effa;padding:14px 18px;border-left:4px solid #27679d}.gold{background:#e6f1eb}.failure{background:#fff0e7}footer{font-size:13px;color:#526270;margin-top:20px}'''


def page(name,title,body):
    OUT.mkdir(parents=True,exist_ok=True)
    run=json.loads((RUN/'run.json').read_text())
    doc=f'<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title><style>{CSS}</style><h1>{html.escape(title)}</h1><div class="subtitle">HW3 Part 2 · Run {run["run_id"]} · {run["started_at"]}<br>Code {run["code_commit"][:12]} · Input freeze {run["freeze_commit"][:12]} · Local CPU MiniLM</div>{body}<footer>Browser view of saved experiment evidence. Source: reports/hw03/raw/part2/{run["run_id"]}/ · No generated answer.</footer>'
    (OUT/f'{name}.html').write_text(doc)


def main():
    console=(RUN/'console.txt').read_text()
    snippets={
      'token':'''parser = TokenTextSplitter(
    chunk_size=192, chunk_overlap=32,
    tokenizer=lambda text: tokenizer.encode(text, add_special_tokens=False),
)
# Each source is split independently; provenance is excluded from embeddings.''',
      'semantic':'''parser = AuditedSemanticSplitter.from_defaults(
    embed_model=embed_model, buffer_size=1,
    breakpoint_percentile_threshold=95,
)
# Subclass only records boundary-buffer token lengths; chunks stay intact.''',
      'sentence_window':'''parser = SentenceWindowNodeParser.from_defaults(
    window_size=3, window_metadata_key="window",
    original_text_metadata_key="original_text",
)
# Embed the central sentence; retain its neighbors as separate context.'''}
    for technique,snippet in snippets.items():
        start=console.index(f'{technique} | Q1 |')
        end=console.index(f'\n{technique} | Q2 |',start)
        exact=console[start:end].strip()
        body=f'<h2>Chunking code excerpt</h2><pre>{html.escape(snippet)}</pre><h2>Actual saved stdout · shared question Q1</h2><pre>{html.escape(exact)}</pre>'
        page(technique,f'{technique.replace("_"," ").title()} retrieval',body)
    summary=json.loads((RUN/'summary.json').read_text())
    rows=''
    for technique,m in summary['baseline']['techniques'].items():
        rows+=f'<tr><td>{technique}</td><td>{m["chunk_count"]}</td><td>{m["average_character_length"]:.1f}</td><td>{m["top1_cosine"]:.4f}</td><td>{m["mean_at_k_cosine"]:.4f}</td><td>{m["source_recall_at_k"]:.2f}</td><td>{m["central_support_at_k"]:.2f}</td><td>{m["context_support_at_k"]:.2f}</td><td>{m["mean_search_latency_ms"]:.3f}</td></tr>'
    body='<h2>Offline regeneration command</h2><pre>.venv-retrieval/bin/python code/retrieval_summarize.py \\\n  --run-dir reports/hw03/raw/part2/baseline-20260920</pre>'
    body+='<h2>Measured macro averages · five frozen questions · k = 3</h2><table><tr><th>Method</th><th>Chunks</th><th>Avg chars</th><th>Top-1 cos</th><th>Mean@3 cos</th><th>Source recall</th><th>Central support</th><th>Context support</th><th>Search ms</th></tr>'+rows+'</table>'
    body+='<p class="note">Source recall counts whether the expected document was retrieved. Answer support requires the requested facts in an individual returned text; these are separate manual judgments. Search timing excludes embeddings and index creation.</p><h2>Truncation audit</h2><table><tr><th>Method</th><th>Indexed texts truncated</th><th>Semantic buffers truncated</th></tr>'
    for technique,stats in summary['technique_stats'].items():
        body+=f'<tr><td>{technique}</td><td>{stats["indexed_truncation_count"]}/{stats["chunk_count"]} ({stats["indexed_truncation_fraction"]:.2%})</td><td>{stats["semantic_buffer_truncation_count"]}/{stats["semantic_buffer_count"]}</td></tr>'
    page('metrics','Retrieval comparison · saved metrics',body+'</table>')
    records=json.loads((RUN/'records.json').read_text())
    q2=next(r for r in records if r['question_id']=='Q2' and r['technique']=='token')
    hit=q2['hits'][0]
    body=f'<h2>Frozen question Q2</h2><p>{html.escape(q2["question"])}</p><p class="gold note">Expected answer in the archived source: $480 for each eligible dependent.</p><h2>Actual rank-1 retrieved text · token method</h2><pre>{html.escape(hit["retrieved_text"])}</pre><p class="failure note">Store score: {hit["store_score"]:.6f} · Explicit cosine: {hit["cosine"]:.6f} · Source: {hit["source_id"]}<br>Manual review: the introduction discusses annual income, deductions and rent calculation, but never gives $480. Central and available-context support are both false.</p><h2>Why this is a high-score failure</h2><p>The query and passage share the terms HUD, income, deductions, and rent calculation. The required numerical amount is absent. Related meaning can score highly without answering the question.</p>'
    page('failure','High similarity without the requested answer',body)


if __name__=='__main__': main()
