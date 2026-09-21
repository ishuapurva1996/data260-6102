// Capture clearly labelled views of the frozen retrieval run for the PDF.
// Does not rerun retrieval or edit the original campaign/screenshots.
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import crypto from 'node:crypto';

const require = createRequire(import.meta.url);
const {chromium} = require(process.env.HW3_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const raw = path.join(root, 'reports/hw03/raw/integration');
const htmlDir = path.join(raw, 'evidence_view');
const shots = path.join(root, 'reports/hw03/screenshots/integration');
const baseline = path.join(root, 'reports/hw03/raw/part2/baseline-20260920');
const read = name => fs.readFileSync(path.join(baseline, name), 'utf8');
const run = JSON.parse(read('run.json'));
const summary = JSON.parse(read('summary.json'));
const stdout = read('console.txt');
const escape = text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const relative = file => path.relative(root, file);
const css = `*{box-sizing:border-box}body{margin:0;padding:24px;background:#fff;color:#17354d;font:22px/1.38 system-ui,sans-serif}h1{font-size:28px;margin:0 0 6px}h2{font-size:22px;margin:18px 0 8px}.meta,footer{font-size:15px;color:#52606b}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7fa;padding:16px;border:1px solid #cbd5df;font:20px/1.35 ui-monospace,Menlo,monospace;margin:16px 0}table{border-collapse:collapse;width:100%;table-layout:fixed;font-size:18px}th,td{border:1px solid #cbd5df;padding:8px;overflow-wrap:anywhere;text-align:left}th{background:#e7f0f4}.note{background:#eef5f5;border-left:4px solid #167d8d;padding:12px 16px}footer{margin-top:16px}`;
fs.mkdirSync(htmlDir, {recursive: true});
fs.mkdirSync(shots, {recursive: true});
function writePage(name, title, body) {
  const doc = `<!doctype html><html><head><meta charset="utf-8"><title>${escape(title)}</title><style>${css}</style></head><body><h1>${escape(title)}</h1>${body}</body></html>`;
  fs.writeFileSync(path.join(htmlDir, name + '.html'), doc);
}
for (const technique of ['token', 'semantic', 'sentence_window']) {
  const start = stdout.indexOf(`${technique} | Q1 |`);
  const end = stdout.indexOf(`\n${technique} | Q2 |`, start);
  if (start < 0 || end < 0) throw new Error('Required Q1 stdout block missing');
  writePage(technique, `${technique.replaceAll('_',' ')} | shared question Q1`, `<pre>${escape(stdout.slice(start,end).trim())}</pre>`);
}
let rows = '';
for (const [name,m] of Object.entries(summary.baseline.techniques)) {
  rows += `<tr><td>${escape(name.replaceAll('_',' '))}</td><td>${m.chunk_count}</td><td>${m.average_character_length.toFixed(1)}</td><td>${m.top1_cosine.toFixed(4)}</td><td>${m.mean_at_k_cosine.toFixed(4)}</td><td>${m.source_recall_at_k.toFixed(2)}</td><td>${m.central_support_at_k.toFixed(2)}</td><td>${m.context_support_at_k.toFixed(2)}</td><td>${m.mean_search_latency_ms.toFixed(3)}</td></tr>`;
}
writePage('metrics', 'Saved comparison | five questions, k = 3', `<h2>Measured macro averages</h2><table><tr><th>Method</th><th>Chunks</th><th>Mean chars</th><th>Top-1 cos</th><th>Mean@3 cos</th><th>Source recall</th><th>Central support</th><th>Context support</th><th>Search ms</th></tr>${rows}</table><p class="note">Source recall asks whether the correct document was retrieved. Answer support asks whether an individual returned text contains the complete answer. Latency measures search with precomputed embeddings.</p><p>Semantic embedding truncation: 76 of 143 chunks (53.15%). Sentence-window context support: 4/5; semantic: 2/5; token: 1/5.</p>`);
const record = JSON.parse(read('records.json')).find(r => r.question_id === 'Q2' && r.technique === 'token');
const hit = record.hits[0];
writePage('failure', 'High similarity without the answer', `<p>${escape(record.question)}</p><p class="note">Expected answer from the archived source: $480 per eligible dependent.<br>Store score ${hit.store_score.toFixed(6)} | Explicit cosine ${hit.cosine.toFixed(6)}</p><h2>Complete rank-1 returned chunk</h2><pre>${escape(hit.retrieved_text)}</pre><p>The passage discusses income and deductions, but never states $480. Source match succeeds; answer support fails.</p>`);

const browser = await chromium.launch({headless:true});
const capture = {captured_at:new Date().toISOString(),browser_version:browser.version(),source_run:run.run_id,viewport:{width:1000,height:600},source_files:{},images:[]};
for (const name of ['run.json','summary.json','console.txt','records.json']) capture.source_files[relative(path.join(baseline,name))] = hash(path.join(baseline,name));
try {
  const page = await browser.newPage({viewport:capture.viewport,deviceScaleFactor:1});
  for (const name of ['token','semantic','sentence_window','metrics','failure']) {
    const source = path.join(htmlDir,name+'.html');
    const destination = path.join(shots,name+'.png');
    await page.goto(pathToFileURL(source).href);
    await page.screenshot({path:destination,fullPage:true});
    const dimensions = await page.evaluate(() => ({width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,overflow:document.documentElement.scrollWidth>innerWidth}));
    if (dimensions.overflow) throw new Error(`Horizontal overflow: ${name}`);
    capture.images.push({name,...dimensions,source:relative(source),source_sha256:hash(source),screenshot:relative(destination),screenshot_sha256:hash(destination)});
  }
} finally { await browser.close(); }
fs.writeFileSync(path.join(raw,'report-screenshot-capture.json'),JSON.stringify(capture,null,2)+'\n');
console.log(JSON.stringify(capture,null,2));
