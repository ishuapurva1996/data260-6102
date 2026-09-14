// Actual Chromium screenshots from the unchanged app, using an isolated server.
// NODE_PATH must include Playwright if it is not installed in this repository.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const net = require('node:net');
const { spawn, execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const RAW = path.join(ROOT, 'reports/hw02/raw/part12');
const PORT = Number(process.env.CAPTURE_PORT || 18702);
const BASE = `http://127.0.0.1:${PORT}`;
const PYTHON = process.env.PYTHON || path.join(ROOT, '.venv-web/bin/python');
const INPUT = {
  listingTitle: 'Downtown San Jose Studio',
  propertyAddress: '999 Main Street, San Jose, CA',
  submitterEmail: 'sanjosedowntownrentalpropertymanagementoffice@example.com',
  description: 'Bright studio with covered parking and convenient light rail access.',
  propertyType: 'apartment', termsAccepted: true,
};
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const timestamp = () => new Date().toISOString();
const manifest = {
  startedAt: timestamp(), baseURL: BASE,
  provenance: 'Unaltered PNG captures produced by Playwright page.screenshot in Chromium. No app DOM, styling, data response, or screenshot pixels are replaced or overlaid. Mutations use actual browser controls and real local HTTP requests.',
  responseBodyLimitation: "Immediate home navigation prevented Playwright from retaining three POST/PUT response bodies; their actual HTTP statuses and request payloads are logged, and authoritative GET snapshots prove the stored records. DELETE 204 correctly has an empty body. Search GET response bodies are available. No mutation body is reconstructed or presented as a captured response.",
  isolation: 'Port 8702 was already occupied by an existing Python process. This capture owns a separate single-worker Uvicorn process on 18702, restarted between Parts 1 and 2. The existing process and its in-memory records were not modified. The submitted main.py default remains PORT_BASE=8702.',
  limitation: 'Headless Chromium screenshots contain page content only; browser chrome and DevTools width toolbar are absent. Each Part 1 original PNG is 375x812 at device scale factor 1. Metadata records the actual innerWidth and document scrollWidth; report captions must state the viewport explicitly. The capture port is an isolated verification port, not the assignment default.',
  screenshots: [], apiSnapshots: [], checkpoints: [], browserConsole: [], pageErrors: [], network: [], serverConsole: [], sourceHashes: {},
};
const pending = new Set();
let stage = 'setup';
let server;
let browser;

function checkpoint(name, detail) {
  const row = { at: timestamp(), stage, name, detail };
  manifest.checkpoints.push(row);
  console.log(`${row.at} ${name}: ${JSON.stringify(detail)}`);
}

async function startServer(part) {
  // Refuse to reuse or kill a listener we do not own.
  const probe = net.createServer();
  await new Promise((resolve, reject) => { probe.once('error', reject); probe.listen(PORT, '127.0.0.1', resolve); });
  await new Promise((resolve) => probe.close(resolve));
  const args = ['-m', 'uvicorn', 'main:app', '--app-dir', path.join(ROOT, 'code/web_application'), '--host', '127.0.0.1', '--port', String(PORT), '--workers', '1'];
  checkpoint('server-start', { part, executable: PYTHON, arguments: args });
  server = spawn(PYTHON, args, { cwd: ROOT, env: { ...process.env, PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
  for (const [streamName, stream] of [['stdout', server.stdout], ['stderr', server.stderr]]) {
    stream.on('data', (chunk) => manifest.serverConsole.push({ at: timestamp(), part, stream: streamName, text: chunk.toString() }));
  }
  let ready = false;
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw Error('Owned capture server exited before ready');
    try { ready = (await fetch(`${BASE}/api/rentals`, { signal: AbortSignal.timeout(500) })).ok; } catch {}
    if (ready) break;
    await delay(100);
  }
  assert(ready, 'Capture server became ready');
  checkpoint('server-ready', { part, pid: server.pid, baseURL: BASE });
}

async function stopServer() {
  if (server && server.exitCode === null) {
    const owned = server;
    const exited = new Promise((resolve) => owned.once('exit', resolve));
    owned.kill('SIGTERM');
    await exited;
    checkpoint('owned-server-stopped', { pid: owned.pid, exitCode: owned.exitCode });
  }
  server = null;
}

async function apiSnapshot(name) {
  const response = await fetch(`${BASE}/api/rentals`);
  assert.equal(response.status, 200);
  const records = await response.json();
  const data = { at: timestamp(), stage, request: { method: 'GET', url: `${BASE}/api/rentals`, purpose: 'Read-only capture checkpoint' }, status: response.status, records };
  const file = `${name}.json`;
  await fs.writeFile(path.join(RAW, file), JSON.stringify(data, null, 2) + '\n');
  manifest.apiSnapshots.push({ file, at: data.at, ids: records.map((r) => r.id) });
  return records;
}

async function newPage(width, height) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(15000);
  page.on('console', (message) => manifest.browserConsole.push({ at: timestamp(), stage, type: message.type(), text: message.text() }));
  page.on('pageerror', (error) => manifest.pageErrors.push({ at: timestamp(), stage, message: error.message }));
  page.on('dialog', async (dialog) => {
    checkpoint('browser-confirmation-accepted', { message: dialog.message() });
    await dialog.accept();
  });
  page.on('request', (request) => {
    if (!new URL(request.url()).pathname.startsWith('/api/')) return;
    manifest.network.push({ event: 'request', at: timestamp(), stage, method: request.method(), url: request.url(), postData: request.postData() });
  });
  page.on('response', (response) => {
    if (!new URL(response.url()).pathname.startsWith('/api/')) return;
    const event = { event: 'response', at: timestamp(), stage, method: response.request().method(), url: response.url(), status: response.status(), statusText: response.statusText() };
    manifest.network.push(event);
    const job = (async () => {
      try { event.body = response.status() === 204 ? '' : await response.text(); }
      catch (error) { event.bodyReadError = error.message; }
    })();
    pending.add(job);
    job.finally(() => pending.delete(job));
  });
  return page;
}

async function waitIDs(page, ids) {
  await page.waitForFunction((expected) => {
    const actual = Array.from(document.querySelectorAll('#rentalList li')).map((el) => Number(el.dataset.id));
    return JSON.stringify(actual) === JSON.stringify(expected) && document.querySelector('#searchForm').getAttribute('aria-busy') === 'false';
  }, ids);
}

async function open(page, suffix, ids) {
  await page.goto(BASE + suffix, { waitUntil: 'networkidle' });
  await waitIDs(page, ids);
}

async function fill(page) {
  for (const name of ['listingTitle', 'propertyAddress', 'submitterEmail', 'description']) await page.locator(`#${name}`).fill(INPUT[name]);
  await page.locator('#propertyType').selectOption(INPUT.propertyType);
  await page.locator('#termsAccepted').check();
}

async function navigate(page, action, ids) {
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), action()]);
  assert.equal(page.url(), BASE + '/');
  await waitIDs(page, ids);
}

async function scroll(page, selector, offset = 18) {
  await page.locator(selector).evaluate((el, top) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - top), offset);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

async function capture(page, part, filename, caption, selector, offset = 18) {
  if (selector) await scroll(page, selector, offset);
  const metrics = await page.evaluate(() => ({
    innerWidth: innerWidth, innerHeight: innerHeight, devicePixelRatio, scrollY,
    documentScrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth,
    visibleIDs: Array.from(document.querySelectorAll('#rentalList li')).map((el) => Number(el.dataset.id)),
    storeSummary: document.querySelector('#storeSummary').textContent,
    searchSummary: document.querySelector('#searchSummary').textContent,
    searchQuery: document.querySelector('#searchQuery').value,
    formStatus: document.querySelector('#formStatus').hidden ? null : document.querySelector('#formStatus').textContent,
    submitDisabled: document.querySelector('#submitButton').disabled,
    createValues: Object.fromEntries(Array.from(document.querySelector('#rentalForm').elements).filter((el) => el.name).map((el) => [el.name, el.type === 'checkbox' ? el.checked : el.value])),
  }));
  assert(metrics.documentScrollWidth <= metrics.innerWidth, 'No horizontal document overflow');
  assert(metrics.bodyScrollWidth <= metrics.innerWidth, 'No horizontal body overflow');
  const relative = `reports/hw02/screenshots/${part}/${filename}.png`;
  const png = await page.screenshot({ path: path.join(ROOT, relative), fullPage: false, animations: 'disabled' });
  const row = { filename: relative, at: timestamp(), stage, caption, url: page.url(), captureType: 'Unaltered viewport screenshot', pngWidth: png.readUInt32BE(16), pngHeight: png.readUInt32BE(20), sha256: createHash('sha256').update(png).digest('hex'), metrics };
  assert.equal(row.pngWidth, metrics.innerWidth);
  assert.equal(row.pngHeight, metrics.innerHeight);
  manifest.screenshots.push(row);
  checkpoint('screenshot', { filename: relative, pixels: [row.pngWidth, row.pngHeight], url: row.url });
}

async function part1() {
  stage = 'P1 baseline';
  await startServer('Part 1');
  const page = await newPage(375, 812);
  await open(page, '/', [1, 2]);
  await apiSnapshot('p1-00-seeds');
  stage = 'P1 true-empty list';
  await navigate(page, () => page.locator('#deleteHighestButton').click(), [1]);
  await navigate(page, () => page.locator('#deleteHighestButton').click(), []);
  assert.deepEqual(await apiSnapshot('p1-01-empty'), []);
  assert(await page.locator('#deleteHighestButton').isDisabled());
  assert.equal(await page.locator('#emptyState').innerText(), 'No rental listings yet. Create your first listing above.');
  await capture(page, 'part1', 'P1-01-empty', 'At an actual 375 × 812 viewport, the empty store shows 0 listings and an explicit no-record message; highest-ID deletion is disabled.', '.list-section');
  stage = 'P1 filled form';
  await open(page, '/?slowSave=true', []);
  await fill(page);
  await capture(page, 'part1', 'P1-02a-form-upper', 'Filled responsive create form at 375px width, upper fields. Single-line inputs may horizontally clip long values.', '#rentalForm');
  await capture(page, 'part1', 'P1-02b-form-lower', 'Filled responsive create form at 375px width, description, property type, terms, and reachable submit control.', '#description', 70);
  stage = 'P1 controlled loading';
  const navigation = page.waitForNavigation({ waitUntil: 'networkidle' });
  const started = Date.now();
  await page.locator('#submitButton').click();
  assert(await page.locator('#submitButton').isDisabled());
  assert.equal(await page.locator('#formStatus').innerText(), 'Saving your rental listing...');
  await capture(page, 'part1', 'P1-03-loading', 'Controlled slowSave=true adds eight seconds before a real POST. Saving status and disabled controls are visible at 375px.', '#description', 55);
  await navigation;
  await waitIDs(page, [1]);
  checkpoint('slow-save-completed', { elapsedMs: Date.now() - started, urlAfter: page.url() });
  const stored = await apiSnapshot('p1-04-created');
  assert.deepEqual(stored, [{ id: 1, ...INPUT }]);
  stage = 'P1 populated mobile list';
  await capture(page, 'part1', 'P1-04-list', 'Actual 375px populated list with new ID 1, long email wrapping in the card, and reachable Edit/Delete controls.', '.list-card');
  await page.getByRole('button', { name: 'Edit listing ID 1', exact: true }).click();
  await capture(page, 'part1', 'P1-05-editor', 'Supplemental 375px editor: ID 1 is prefilled and Save changes/Cancel remain reachable.', '#updateForm');
  await page.locator('#cancelEditButton').click();
  stage = 'P1 controlled UI error';
  await open(page, '/?simulateError=true', [1]);
  await fill(page);
  const postBefore = manifest.network.filter((row) => row.event === 'request' && row.method === 'POST').length;
  await page.locator('#submitButton').click();
  await page.waitForFunction(() => !document.querySelector('#submitButton').disabled && document.querySelector('#formStatus').classList.contains('status-error'));
  assert.equal(await page.locator('#listingTitle').inputValue(), INPUT.listingTitle);
  assert(await page.locator('#termsAccepted').isChecked());
  const postAfter = manifest.network.filter((row) => row.event === 'request' && row.method === 'POST').length;
  assert.equal(postAfter, postBefore);
  assert.deepEqual(await apiSnapshot('p1-06-after-controlled-error'), stored);
  checkpoint('controlled-error-no-post', { postRequestsDuringError: postAfter - postBefore, storedIDs: [1], retainedInput: true, controlsEnabled: true });
  await capture(page, 'part1', 'P1-06-error', 'Controlled simulateError=true UI failure: visible error, retained lower form input, and restored controls. No POST or backend rejection occurs.', '#description', 40);
  await capture(page, 'part1', 'P1-06b-retained-upper', 'Supplemental retained title, address, and email after the controlled UI error; original viewport remains 375 × 812.', '#rentalForm');
  await page.close();
  await stopServer();
}

async function part2() {
  stage = 'P2 fresh baseline';
  await startServer('Part 2');
  const page = await newPage(1100, 1100);
  await open(page, '/', [1, 2]);
  const before = await apiSnapshot('p2-00-seeds');
  assert.deepEqual(before.map((r) => r.id), [1, 2]);
  await capture(page, 'part2', 'P2-00-seeds', 'Fresh isolated app instance contains original seed IDs 1 and 2.', '.list-section');
  stage = 'P2 Q1 create';
  await fill(page);
  await capture(page, 'part2', 'P2-Q1-input', 'Create input for Downtown San Jose Studio before submission.', '#rentalForm');
  await navigate(page, () => page.locator('#submitButton').click(), [1, 2, 3]);
  const created = await apiSnapshot('p2-q1-after-create');
  assert.deepEqual(created, [...before, { id: 3, ...INPUT }]);
  await capture(page, 'part2', 'P2-Q1-created', 'Create returned home with newly assigned ID 3; its title, address, and remaining fields are displayed.', '#rental-3', 360);
  stage = 'P2 Q2 update ID1';
  await page.getByRole('button', { name: 'Edit listing ID 1', exact: true }).click();
  assert.equal(await page.locator('#updateTitle').inputValue(), before[0].listingTitle);
  assert.equal(await page.locator('#updateAddress').inputValue(), before[0].propertyAddress);
  await capture(page, 'part2', 'P2-Q2-before', 'Before update: editor targets ID 1 with its original title and address prefilled.', '#updateForm');
  const updates = { listingTitle: 'Updated Downtown Apartment', propertyAddress: '900 Market Street, San Jose, CA' };
  await page.locator('#updateTitle').fill(updates.listingTitle);
  await page.locator('#updateAddress').fill(updates.propertyAddress);
  await navigate(page, () => page.locator('#updateButton').click(), [1, 2, 3]);
  const updated = await apiSnapshot('p2-q2-after-update');
  assert.deepEqual(updated, created.map((r) => r.id === 1 ? { ...r, ...updates } : r));
  await capture(page, 'part2', 'P2-Q2-updated', 'ID 1 now has Updated Downtown Apartment and 900 Market Street, San Jose, CA. Other fields and IDs 2 and 3 remain unchanged.', '.list-card');
  stage = 'P2 Q3 delete highest';
  await apiSnapshot('p2-q3-before-delete');
  await capture(page, 'part2', 'P2-Q3-before', 'Before deletion: total 3, highest ID 3, and global Delete highest-ID listing (3) action.', '.list-card');
  await navigate(page, () => page.locator('#deleteHighestButton').click(), [1, 2]);
  const after = await apiSnapshot('p2-q3-after-delete');
  assert.deepEqual(after, updated.filter((r) => r.id !== 3));
  await capture(page, 'part2', 'P2-Q3-after', 'The actual highest-ID DELETE returned 204; home now displays only IDs 1 and 2, total 2 and highest ID 2.', '.list-section');
  stage = 'P2 Q4 search';
  async function search(query, expected, filename, caption) {
    await page.locator('#searchQuery').fill(query);
    await Promise.all([page.waitForResponse((r) => r.request().method() === 'GET' && new URL(r.url()).searchParams.get('q') === query), page.locator('#searchButton').click()]);
    await waitIDs(page, expected);
    await capture(page, 'part2', filename, caption, '.list-section');
  }
  await search('Downtown', [1], 'P2-Q4-title', 'Title-only search Downtown returns ID 1. Downtown is absent from its address; the global store still contains two records.');
  await search('Market', [1], 'P2-Q4-address', 'Address-only search Market returns ID 1. Market is absent from its title; the global store still contains two records.');
  await page.locator('#clearSearchButton').click();
  await waitIDs(page, [1, 2]);
  await capture(page, 'part2', 'P2-Q4-clear', 'Clear restores the two remaining records and an empty search query.', '.list-section');
  await search('no-such-rental-6102', [], 'P2-Q4-no-match', 'Supplemental no-match state retains the global two-record summary; this is distinct from Part 1’s truly empty store.');
  await page.locator('#clearSearchButton').click();
  await waitIDs(page, [1, 2]);
  assert.deepEqual(await apiSnapshot('p2-final-records'), after);
  await page.close();
  await stopServer();
}

async function main() {
  await fs.mkdir(RAW, { recursive: true });
  for (const part of ['part1', 'part2']) await fs.mkdir(path.join(ROOT, 'reports/hw02/screenshots', part), { recursive: true });
  manifest.headAtCapture = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: ROOT, encoding: 'utf8' }).trim();
  manifest.sourceWorkingTreeStatus = execFileSync('git', ['status', '--short', '--', 'code/web_application'], { cwd: ROOT, encoding: 'utf8' }).trim();
  for (const file of ['main.py', 'static/index.html', 'static/styles.css', 'static/app.js']) {
    const data = await fs.readFile(path.join(ROOT, 'code/web_application', file));
    manifest.sourceHashes[`code/web_application/${file}`] = createHash('sha256').update(data).digest('hex');
  }
  try {
    browser = await chromium.launch({ headless: true });
    manifest.browserVersion = browser.version();
    manifest.playwrightVersion = require('playwright/package.json').version;
    await part1();
    await part2();
    assert.deepEqual(manifest.pageErrors, []);
    manifest.outcome = 'PASS';
    checkpoint('capture-complete', { screenshots: manifest.screenshots.length, unexpectedPageErrors: manifest.pageErrors.length });
  } catch (error) {
    manifest.outcome = 'FAIL';
    manifest.failure = error.stack;
    throw error;
  } finally {
    await Promise.allSettled([...pending]);
    await stopServer();
    if (browser) await browser.close();
    manifest.finishedAt = timestamp();
    await fs.writeFile(path.join(RAW, 'capture-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
    await fs.writeFile(path.join(RAW, 'network-events.json'), JSON.stringify(manifest.network, null, 2) + '\n');
    await fs.writeFile(path.join(RAW, 'server-console.txt'), manifest.serverConsole.map((r) => `[${r.at}] [${r.part}] [${r.stream}] ${r.text}`).join(''));
    await fs.writeFile(path.join(ROOT, 'reports/hw02/RUN_LOG_PART12.txt'), [
      'HW2 Parts 1 and 2 — actual browser capture run',
      `Started: ${manifest.startedAt}`, `Finished: ${manifest.finishedAt}`, `Outcome: ${manifest.outcome}`,
      `HEAD at capture: ${manifest.headAtCapture}`, `Web source working-tree status: ${manifest.sourceWorkingTreeStatus || 'clean'}`,
      `Chromium: ${manifest.browserVersion}; Playwright: ${manifest.playwrightVersion}`,
      `Capture server: ${BASE}`, manifest.isolation, manifest.provenance, manifest.limitation,
      'Controlled modes: slowSave=true delays a real POST by eight seconds; simulateError=true throws a UI error after two seconds without sending a POST. Neither is a measured backend outage.',
      'Capture script: scripts/capture_part12.cjs',
      'Raw manifest: reports/hw02/raw/part12/capture-manifest.json',
      'Actual request/response metadata and available bodies: reports/hw02/raw/part12/network-events.json',
      manifest.responseBodyLimitation,
      'Timestamped Uvicorn output: reports/hw02/raw/part12/server-console.txt',
      '', ...manifest.checkpoints.map((r) => `${r.at} ${r.stage} | ${r.name}: ${JSON.stringify(r.detail)}`),
      '', 'Server console (timestamp prefixed as received):', ...manifest.serverConsole.map((r) => `[${r.at}] [${r.part}] ${r.text}`),
    ].join('\n') + '\n');
  }
}

main().catch((error) => { console.error(error.stack); process.exitCode = 1; });
