#!/usr/bin/env node
'use strict';
// Genuine browser screenshots of saved experiment records, never simulated UI.
const fs = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { createHash } = require('node:crypto');
const PLAYWRIGHT = process.env.HW04_PLAYWRIGHT_PATH || '/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright';
const { chromium } = require(PLAYWRIGHT);
const ROOT = path.resolve(__dirname, '..');
const TITLE = 'Saved local experiment output — browser capture';
const METHOD = 'Playwright Chromium full-page screenshots of HTML rendered from saved raw JSON/transcript records, with verbatim source excerpts. No model calls, image reconstruction, or simulated terminal.';
const sha = value => createHash('sha256').update(value).digest('hex');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const rel = value => path.relative(ROOT, value).split(path.sep).join('/');
const read = filename => fs.readFile(filename, 'utf8');
const json = async filename => JSON.parse(await read(filename));
const jsonl = async filename => (await read(filename)).trim().split('\n').filter(Boolean).map(JSON.parse);
const pre = (value, cls = '') => `<pre class="${cls}">${esc(typeof value === 'string' ? value : JSON.stringify(value, null, 2))}</pre>`;
const table = (headers, rows) => `<table><thead><tr>${headers.map(v => `<th>${esc(v)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(v => `<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
function args(argv) {
  const options = {};
  for (let i = 0; i < argv.length; i += 2) {
    if (!['--run', '--output'].includes(argv[i]) || !argv[i + 1]) throw Error('Usage: capture_hw04_part4.cjs --run <run-dir> --output <new-screenshot-dir>');
    options[argv[i].slice(2)] = path.resolve(ROOT, argv[i + 1]);
  }
  if (!options.run || !options.output) throw Error('Both --run and --output are required');
  if (options.output === options.run || options.output.startsWith(options.run + path.sep)) throw Error('Screenshots must be outside the immutable experiment directory');
  return options;
}
function document(title, body, runId) {
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(title)}</title>
<style>*{box-sizing:border-box}html{background:#edf1f5;color:#172434}body{margin:0;font:18px/1.5 Arial,sans-serif}main{width:1250px;padding:36px 42px 42px;margin:0 auto;background:#fff}h1{font-size:26px;line-height:1.25;margin:0 0 10px}h2{font-size:23px;line-height:1.3;margin:22px 0 10px}h3{font-size:19px;line-height:1.3;margin:18px 0 8px}p{margin:8px 0 14px}.eyebrow{color:#344a67;font-weight:700;font-size:17px}.notice{border-left:5px solid #426389;padding:10px 15px;background:#f2f5f9}.meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:14px 0}.meta div{background:#f0f4f8;padding:9px 12px;overflow-wrap:anywhere;font-size:16px}.meta strong{display:block;font-size:15px;color:#40536b}pre{font:16px/1.48 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;padding:15px 18px;margin:7px 0 16px;background:#f4f6f8;border:1px solid #d2dce6;border-radius:5px}pre.answer{font-size:18px;line-height:1.6;background:#f7fbf7;border-left:5px solid #477458}pre.code{font-size:16px;line-height:1.42;color:#eaf1fa;background:#19293b;border:none}.source{font-size:15px;color:#455c76;overflow-wrap:anywhere}.question{font-size:21px;line-height:1.45;font-weight:600}table{border-collapse:collapse;width:100%;table-layout:fixed;margin:12px 0 20px;font-size:16px;line-height:1.4}th,td{border:1px solid #bfcddc;text-align:left;vertical-align:top;padding:10px;overflow-wrap:anywhere}th{background:#dfe9f4}footer{border-top:1px solid #c8d3df;margin-top:26px;padding-top:12px;font-size:14px;color:#526275;overflow-wrap:anywhere}.pair{margin:18px 0}.raw-label{color:#2e583c}</style>
<main><div class="eyebrow">HW4 · Part 4 · ${esc(runId)}</div><h1>${TITLE}</h1><p class="notice">This is a browser-rendered view of saved local experiment evidence. Model answers below are unedited. The page does not claim to be a live model interface.</p><h2>${esc(title)}</h2>${body}<footer>Capture created from saved artifacts. Full source paths, SHA-256 hashes, browser version, rendering checks, and capture time are recorded in manifest.json.</footer></main></html>`;
}
async function sourceExcerpt(file, startNeedle, endNeedle, limit = 50) {
  const full = await read(file);
  const lines = full.split('\n');
  const start = lines.findIndex(line => line.includes(startNeedle));
  if (start < 0) throw Error(`Missing source anchor ${startNeedle} in ${file}`);
  const end = endNeedle ? lines.findIndex((line, i) => i > start && line.includes(endNeedle)) : start + limit;
  if (end < 0) throw Error(`Missing closing source anchor ${endNeedle} in ${file}`);
  const boundedEnd = Math.min(end, start + limit, lines.length);
  const excerpt = lines.slice(start, boundedEnd).map((line, i) => `${String(start + i + 1).padStart(4)}  ${line}`).join('\n');
  return { file, full, start_line: start + 1, end_line: boundedEnd, sha256: sha(full), excerpt };
}
const codeBlock = source => `<div class="source">Verbatim code excerpt · ${esc(rel(source.file))}:${source.start_line}–${source.end_line}</div>${pre(source.excerpt, 'code')}`;
function metadata(entries) { return `<div class="meta">${entries.map(([key, value]) => `<div><strong>${esc(key)}</strong>${esc(value ?? 'N/A')}</div>`).join('')}</div>`; }
async function main() {
  const { run, output } = args(process.argv.slice(2));
  const [runMeta, rows, index, config, corpus, chunks, sweep, summary] = await Promise.all([
    json(path.join(run, 'run_metadata.json')), jsonl(path.join(run, 'responses.jsonl')),
    json(path.join(run, 'index_audit.json')), json(path.join(run, 'frozen/experiment_config.json')),
    json(path.join(run, 'frozen/reports/hw04/part4/CORPUS_MANIFEST.json')), jsonl(path.join(run, 'chunks.jsonl')),
    json(path.join(run, 'sweep_references.json')), json(path.join(run, 'summary.json'))
  ]);
  const runId = path.basename(run);
  const mainRows = rows.filter(row => row.phase === 'main');
  if (rows.length !== 22 || mainRows.length !== 18 || new Set(rows.map(row => row.response_id)).size !== 22 || sweep.length !== 6) throw Error('Capture requires 22 unique responses, 18 main responses and 6 sweep references');
  if (rows.some(row => row.answer !== row.raw_response?.response && row.status !== 'failed')) throw Error('Saved answer does not exactly match raw model response');
  if (summary.run_id !== runId || !summary.configurations) throw Error('Summary belongs to a different run or has no configuration table');
  // mkdir without recursive final component prevents accidental overwriting.
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.mkdir(output);
  const pipeline = path.join(run, 'frozen/src/rag/pipeline.py');
  const runner = path.join(run, 'frozen/src/rag/runner.py');
  const promptCode = {};
  for (const letter of ['A', 'B', 'C']) {
    promptCode[letter] = await sourceExcerpt(pipeline, `${letter === 'A' ? 'if' : 'elif'} configuration == "${letter}":`, letter === 'A' ? 'elif configuration == "B":' : letter === 'B' ? 'elif configuration == "C":' : '    else:', 25);
  }
  const chunkCode = await sourceExcerpt(pipeline, '    while start < len(text):', '        original_tokens =', 10);
  const indexCode = await sourceExcerpt(runner, '    index = build_index(nodes, embed)', '    fingerprint =', 10);
  const retrievalCode = await sourceExcerpt(runner, '    # Durably save the exact request', '    try:', 25);
  const sourceFiles = [];
  const panels = [];
  function panel(id, title, body, items, responseIds, files, snippets = [], exact = []) {
    const p = { id, title, body, items, responseIds, files, snippets, exact };
    panels.push(p); sourceFiles.push(...files); return p;
  }
  const chunkSample = chunks.find(chunk => chunk.source_id === 'EPA_DISCLOSURE') || chunks[0];
  panel('01-corpus-index-chunks', 'Five documents, chunking, and the real vector index',
    table(['Source ID', 'Document snapshot', 'SHA-256'], corpus.sources.map(s => [s.source_id, s.title, s.sha256])) +
    metadata([['Chunk maximum', `${config.chunk_size} ${config.chunk_unit}`], ['Requested overlap', `${config.chunk_overlap} ${config.chunk_unit}`], ['Embedding model', config.model_name]]) +
    `<section class="pair">${codeBlock(chunkCode)}<h3>Saved chunk sample</h3>${pre({chunk_id:chunkSample.chunk_id, source_id:chunkSample.source_id, location:chunkSample.location, characters:chunkSample.characters, embedding_tokens:chunkSample.embedding_tokens, requested_overlap:chunkSample.requested_overlap, actual_overlap:chunkSample.actual_overlap, text:chunkSample.text})}</section>` +
    `<section class="pair">${codeBlock(indexCode)}<h3>Actual index construction audit</h3>${pre(index)}</section>`,
    ['R1','R8','corpus','index','chunk_setup'], [], ['run_metadata.json','frozen/experiment_config.json','frozen/reports/hw04/part4/CORPUS_MANIFEST.json','chunks.jsonl','index_audit.json'].map(f => path.join(run,f)), [chunkCode,indexCode]);
  for (const row of rows) {
    const raw = row.raw_response || {};
    const labels = Object.entries(row.source_labels || {});
    const labelRows = labels.map(([label, hit]) => [`[${label}]`, hit.source_id, hit.location, hit.chunk_id]);
    const body = `<p class="question">${esc(row.question)}</p>` + metadata([
      ['Response ID',row.response_id], ['Configuration / phase',`${row.configuration} / ${row.phase}`], ['Requested k',row.requested_k],
      ['Returned / retained chunks',`${row.returned_count} / ${row.retained_count}`], ['Completion status',`${row.status}; done=${raw.done ?? 'N/A'}; reason=${raw.done_reason ?? 'N/A'}`], ['Local model',row.request?.model],
      ['Actual prompt / output tokens',`${raw.prompt_eval_count ?? 'N/A'} / ${raw.eval_count ?? 'N/A'}`], ['Evidence / prompt token bound',`${row.evidence_token_bound} / ${row.prompt_token_bound}`], ['Generation seconds',Number(row.generation_seconds).toFixed(3)],
      ['Generation started',row.generation_started_at], ['Generation finished',row.finished_at], ['Window / answer reserve',`${row.window} / ${row.answer_token_reserve}`]
    ]) + `<section class="pair">${codeBlock(promptCode[row.configuration])}<h3 class="raw-label">Unedited model response</h3><pre class="answer" id="raw-answer">${esc(row.answer ?? '')}</pre>${row.error ? `<h3>Recorded failure</h3>${pre(row.error)}` : ''}</section>` +
    `<h3>Source-number mapping supplied to the model</h3>${labels.length ? table(['Label','Source','Location','Chunk ID'],labelRows) : `<p>${row.configuration === 'A' ? 'No document evidence was supplied to A.' : 'No numbered source labels were supplied in this prompt.'}</p>`}` +
    `<h3>Exact saved application prompt</h3><pre id="raw-prompt">${esc(row.prompt)}</pre>` +
    (row.request?.raw ? `<h3>Exact raw wire prompt sent to Ollama</h3><pre id="wire-prompt">${esc(row.request.prompt)}</pre>` : '') +
    (row.configuration === 'C' ? `<h3>Recorded context-selection decisions</h3>${pre(row.decisions)}` : '') +
    `<p class="source">Token accounting method: ${esc(row.token_count_method)}. Runtime counts above come directly from the saved Ollama response.</p>`;
    panel(row.response_id, `${row.question_id} · Configuration ${row.configuration} · k=${row.requested_k}`, body,
      ['R3','R4','R8',row.question_id,`configuration_${row.configuration}`,...(row.phase === 'sweep' || row.question_id === sweep[0].question_id && row.configuration !== 'A' ? ['R5','sweep'] : [])],
      [row.response_id], [path.join(run,'responses.jsonl')], [promptCode[row.configuration]], [['#raw-answer',row.answer ?? ''],['#raw-prompt',row.prompt], ...(row.request?.raw ? [['#wire-prompt',row.request.prompt]] : [])]);
  }
  const transcriptFile = path.join(run,'RUN_LOG.txt');
  const transcript = await read(transcriptFile);
  const retrievalRow = mainRows.find(row => row.question_id === 'Q2' && row.configuration === 'B') || mainRows.find(row => row.configuration === 'B');
  const marker = `GENERATION START ${retrievalRow.response_id}`;
  const generationIndex = transcript.indexOf(marker);
  const preceding = transcript.slice(0,generationIndex);
  const retrievalMarker = new RegExp(`\\[[^\\]]+\\] RETRIEVAL ${retrievalRow.question_id} requested=${retrievalRow.requested_k} returned=\\d+`, 'g');
  const matches = [...preceding.matchAll(retrievalMarker)];
  if (generationIndex < 0 || !matches.length) throw Error('No genuine pre-generation retrieval transcript found');
  const excerpt = transcript.slice(matches[matches.length-1].index, transcript.indexOf('\n',generationIndex));
  panel('02-retrieval-before-generation', 'Retrieved chunks printed before generation',
    metadata([['Response ID',retrievalRow.response_id],['Question',retrievalRow.question_id],['Requested k',retrievalRow.requested_k]]) +
    `<section class="pair">${codeBlock(retrievalCode)}<h3>Exact saved transcript excerpt</h3><p>The final line records the generation start after the printed retrieval block.</p><pre id="retrieval-transcript">${esc(excerpt)}</pre></section>`,
    ['R2','R8','pre_generation_retrieval'], [retrievalRow.response_id], [transcriptFile,path.join(run,'responses.jsonl')], [retrievalCode], [['#retrieval-transcript',excerpt]]);
  let evaluationFile = path.join(run,'frozen/src/rag/evaluation.py');
  let evaluatorSnapshot = 'Frozen evaluation source';
  try { await fs.access(evaluationFile); } catch {
    evaluationFile = path.join(ROOT,'src/rag/evaluation.py');
    const snapshotDir = path.join(output,'source_snapshots');
    await fs.mkdir(snapshotDir);
    const snapshot = path.join(snapshotDir,'evaluation.py');
    await fs.copyFile(evaluationFile,snapshot);
    evaluationFile = snapshot;
    evaluatorSnapshot = 'Evaluation-time source snapshot (saved with these captures; created after generation)';
  }
  const evalText = await read(evaluationFile);
  const evalAnchor = evalText.includes('def summarize(') ? 'def summarize(' : evalText.includes('def summarize_') ? 'def summarize_' : 'def ';
  const evalCode = await sourceExcerpt(evaluationFile,evalAnchor,null,18);
  const metricNames = [ ['correct_retrieval','Full retrieval Q1–Q3'], ['final_context_coverage','Final coverage Q1–Q3'], ['accuracy','Accuracy all six'], ['answerable_accuracy','Accuracy Q1–Q3'], ['faithfulness','Faithfulness claims'], ['format_compliance','Format'], ['robustness','Robustness Q4–Q6'], ['required_refusal','Q5/Q6 refusal'], ['exact_required_refusal','Q5/Q6 exact refusal'] ];
  const evalRows = metricNames.map(([key,title]) => [title,...['A','B','C'].map(letter => summary.configurations[letter]?.[key]?.display ?? 'N/A')]);
  panel('03-evaluation-summary', 'Evaluation from saved semantic judgments',
    `<p>Evaluator: ${esc(summary.evaluator)}. ${esc(summary.method)}</p>${metadata([['Main responses',summary.main_response_count],['Distinct model calls',summary.distinct_response_count],['Sweep references',summary.sweep_reference_count]])}` +
    `<section class="pair"><p class="source">${esc(evaluatorSnapshot)}</p>${codeBlock(evalCode)}<h3>Saved summary fractions (numerator / denominator)</h3>${table(['Metric','A: No RAG','B: Basic RAG','C: Context RAG'],evalRows)}</section><p class="notice">N/A remains distinct from a failed score. Sweep responses are excluded from the 18-response main summary. Semantic judgments were made by the assistant against saved evidence; screenshot rendering does not validate those judgments.</p>`,
    ['R6','R7','R8','evaluation'], mainRows.map(row => row.response_id), [path.join(run,'summary.json'),evaluationFile], [evalCode]);
  const evidenceInputs = [...new Set(sourceFiles.concat(panels.flatMap(p => p.snippets.map(s => s.file))))];
  const inputHashes = {};
  for (const file of evidenceInputs) inputHashes[rel(file)] = sha(await fs.readFile(file));
  const manifest = {schema_version:1,run_id:runId,method:METHOD,created_at:new Date().toISOString(),run_started_at:runMeta.started_at,captures:[],sweep_references:[],source_hashes:inputHashes};
  const browser = await chromium.launch({headless:true});
  try {
    for (const p of panels) {
      const htmlPath = path.join(output,`${p.id}.html`);
      const pngPath = path.join(output,`${p.id}.png`);
      const html = document(p.title,p.body,runId);
      await fs.writeFile(htmlPath,html);
      const page = await browser.newPage({viewport:{width:1250,height:900},deviceScaleFactor:1});
      await page.route('**/*', route => route.request().url().startsWith('file:') ? route.continue() : route.abort());
      await page.goto(pathToFileURL(htmlPath).href,{waitUntil:'load'});
      await page.evaluate(() => document.fonts.ready);
      for (const [selector,expected] of p.exact) {
        const actual = await page.locator(selector).textContent();
        if (actual !== expected) throw Error(`Rendered raw text differs: ${p.id} ${selector}`);
      }
      const metrics = await page.evaluate(() => ({viewport_width:innerWidth,document_width:document.documentElement.scrollWidth,document_height:document.documentElement.scrollHeight,overflow_elements:[...document.querySelectorAll('main *')].filter(el => el.scrollWidth > el.clientWidth + 1).map(el => el.tagName)}));
      if (metrics.document_width > 1250 || metrics.overflow_elements.length) throw Error(`Horizontal clipping detected: ${p.id} ${JSON.stringify(metrics)}`);
      const png = await page.screenshot({path:pngPath,fullPage:true,animations:'disabled'});
      manifest.captures.push({path:rel(pngPath),sha256:sha(png),html_path:rel(htmlPath),html_sha256:sha(html),items:p.items,response_ids:p.responseIds,description:p.title,source_files:[...new Set(p.files.concat(p.snippets.map(s => s.file)))].map(rel),source_excerpts:p.snippets.map(s => ({path:rel(s.file),start_line:s.start_line,end_line:s.end_line,sha256:s.sha256})),captured_at:new Date().toISOString(),width:png.readUInt32BE(16),height:png.readUInt32BE(20),browser_version:browser.version(),playwright_version:require(path.join(PLAYWRIGHT,'package.json')).version,render_checks:{...metrics,exact_raw_text_checks:p.exact.length,no_horizontal_clipping:true}});
      await page.close();
    }
  } finally { await browser.close(); }
  for (const row of sweep) {
    const capture = manifest.captures.find(c => c.response_ids.length === 1 && c.response_ids[0] === row.response_id && !c.items.includes('pre_generation_retrieval'));
    if (!capture || row.reused_main !== (row.k === 3)) throw Error(`Invalid sweep capture reference: ${row.response_id}`);
    manifest.sweep_references.push({...row,capture_path:capture.path,reused_main:row.k === 3});
  }
  for (const file of evidenceInputs) if (inputHashes[rel(file)] !== sha(await fs.readFile(file))) throw Error(`Input changed during capture: ${file}`);
  manifest.completed_at = new Date().toISOString();
  await fs.writeFile(path.join(output,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  console.log(JSON.stringify({run_id:runId,captures:manifest.captures.length,response_captures:rows.length,sweep_references:manifest.sweep_references.length,manifest:rel(path.join(output,'manifest.json')),all_render_checks_pass:true},null,2));
}
main().catch(error => {console.error(error.stack);process.exitCode=1;});
