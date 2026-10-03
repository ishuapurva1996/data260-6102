#!/usr/bin/env node
// Uses the owner's running server. Never launches a server or resets a database.
// NODE_PATH must include Playwright if it is provided by the bundled runtime.
// HW5_BASE_URL=https://localhost:8702 HW5_RAW_DIR=<explicit evidence directory>
// node tests/browser_hw05_part1.cjs --mock|--real
// Real mode needs private HW4_SEED_EMAIL/HW4_SEED_PASSWORD (or HW5_ equivalents).
// HW5_SCREENSHOTS_DIR is optional; screenshots are genuine UI only, not paired Redux frames.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID, createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..');
const MODE = process.argv.includes('--mock') ? 'mock' : 'real';
const BASE = (process.env.HW5_BASE_URL || 'https://localhost:8702').replace(/\/$/, '');
const RAW = process.env.HW5_RAW_DIR;
const SHOTS = process.env.HW5_SCREENSHOTS_DIR;
const EMAIL = MODE === 'mock' ? 'browser@example.com' : process.env.HW5_SEED_EMAIL || process.env.HW4_SEED_EMAIL;
const PASSWORD = MODE === 'mock' ? 'mock-password' : process.env.HW5_SEED_PASSWORD || process.env.HW4_SEED_PASSWORD;
const now = () => new Date().toISOString();
const delay = (ms) => new Promise((done) => setTimeout(done, ms));
const report = { mode: MODE, status: 'running', started_at: now(), base_url: BASE, checks: [], screenshots: [], limitations: [
  MODE === 'mock' ? 'Mock HTTP responses prove UI behavior only; no MySQL/authentication security evidence.' : 'Live HTTPS/MySQL service supplied by owner; this test creates and deletes only uniquely marked test data.',
  'UI screenshots do not substitute for the required source-snippet/UI Redux frames or Postman evidence.',
] };
const redact = (value) => String(value).replaceAll(PASSWORD || '\0', '[REDACTED]').replace(/(s6102_session=)[^;\s]+/gi, '$1[REDACTED]');
const match = (method, pathname) => (response) => response.request().method() === method && new URL(response.url()).pathname === pathname;
const card = (page, id) => page.locator(`article[data-record-id="${id}"]`);
const ids = (page) => page.locator('article').evaluateAll((rows) => rows.map((row) => Number(row.dataset.recordId)));
async function bounded(promise, label, milliseconds = 15000) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Timed out after ${milliseconds} ms: ${label}`)), milliseconds);
    })]);
  } finally { clearTimeout(timer); }
}
const heldGates = new Set();
function gate() {
  let release;
  const promise = new Promise((done) => { release = done; });
  const resolve = () => { heldGates.delete(resolve); release(); };
  heldGates.add(resolve);
  return { promise, resolve, wait: (label) => bounded(promise, label) };
}
async function check(name, operation) {
  const entry = { name, started_at: now() }; report.checks.push(entry);
  console.log(`RUN [${MODE}] ${name}`);
  try { entry.details = await bounded(operation(), name, 45000); entry.status = 'pass'; console.log(`PASS [${MODE}] ${name}`); }
  catch (error) { entry.status = 'fail'; entry.error = redact(error.stack); throw error; }
  finally { entry.finished_at = now(); }
}
async function snapshot(page, name) {
  const size = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
  assert(size.document <= size.viewport && size.body <= size.viewport, `Horizontal overflow: ${JSON.stringify(size)}`);
  if (!SHOTS) return { dimensions: size, screenshot: 'not requested' };
  const filename = path.resolve(SHOTS, `${MODE}-${name}.png`);
  await page.screenshot({ path: filename, fullPage: false, animations: 'disabled', mask: [page.locator('input[type=password]')] });
  const result = { file: filename, actual_url: page.url(), mode: MODE, captured_at: now(), dimensions: size };
  report.screenshots.push(result); return result;
}
async function home(page) {
  await page.waitForURL(`${BASE}/`);
  await page.locator('.result-count').waitFor();
}
async function login(page, navigate = true) {
  if (navigate) await page.goto(`${BASE}/login`);
  await page.getByLabel('Email', { exact: true }).fill(EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  const response = page.waitForResponse(match('POST', '/api/auth/login'));
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  assert.equal((await response).status(), 200); await home(page);
}
async function fill(page, values) {
  // Router transitions may leave the old Update form visible briefly. Wait for
  // the destination heading before filling fields shared by Create and Update.
  await page.getByRole('heading', {
    name: values.submitterEmail !== undefined ? 'Add a rental listing' : 'Update listing', exact: true,
  }).waitFor();
  for (const [field, label] of [['listingTitle', 'Listing title'], ['propertyAddress', 'Property address'], ['availableUnits', 'Available units']])
    if (values[field] !== undefined) await page.getByLabel(label, { exact: true }).fill(String(values[field]));
  if (values.listingCode !== undefined) await page.locator('[name=listingCode]').fill(values.listingCode);
  if (values.managerId !== undefined) {
    await page.locator(`[name=managerId] option[value="${values.managerId}"]`).waitFor({ state: 'attached' });
    await page.getByLabel('Property manager', { exact: true }).selectOption(String(values.managerId));
  }
  if (values.submitterEmail !== undefined) {
    await page.getByLabel('Landlord Email', { exact: true }).fill(values.submitterEmail);
    await page.getByLabel('Description', { exact: true }).fill(values.description);
    await page.getByLabel('Property type', { exact: true }).selectOption(values.propertyType);
    await page.getByLabel('I accept the terms', { exact: true }).check();
  }
}
async function search(page, query) {
  await page.getByLabel('Search listings').fill(query);
  const response = page.waitForResponse(match('GET', '/api/rentals'));
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await response; await home(page);
}
const fixture = (id) => ({ id, listingTitle: `Quiet rental ${id}`, propertyAddress: `${id} Browser Lane`,
  submitterEmail: 'browser-owner@example.com', description: 'A sunny rental with room to study and a private garden.',
  propertyType: 'apartment', termsAccepted: true, listingCode: `S6102-R-${id}`, availableUnits: 1, managerId: 1,
  createdAt: '2026-10-03T00:00:00Z', updatedAt: '2026-10-03T00:00:00Z' });
const createFields = (title, managerId = 1) => ({ listingTitle: title, propertyAddress: '8702 Browser Lane',
  submitterEmail: 'browser-owner@example.com', description: 'A sunny rental with room to study and a private garden.',
  propertyType: 'apartment', termsAccepted: true, availableUnits: 2, managerId });
async function mockRoutes(context, state) {
  await context.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const request = route.request(), url = new URL(request.url()), method = request.method(), pathname = url.pathname;
    const body = method === 'GET' ? undefined : request.postDataJSON();
    const entry = { method, path: pathname, query: url.search }; state.requests.push(entry);
    if (pathname.startsWith('/api/rentals') && body) entry.body = body;
    const respond = (status, data, total) => route.fulfill({ status, contentType: 'application/json',
      headers: total === undefined ? {} : { 'X-Total-Count': String(total) }, body: status === 204 ? '' : JSON.stringify(data) });
    const index = state.faults.findIndex((fault) => fault.method === method && fault.path === pathname && (!fault.query || fault.query === url.searchParams.get('q')));
    if (index >= 0) {
      const fault = state.faults.splice(index, 1)[0];
      if (fault.entered) { console.log(`CONTROL entered ${method} ${pathname}`); fault.entered.resolve(); }
      if (fault.gate) await bounded(fault.gate.promise, `release ${method} ${pathname}`, 30000);
      if (fault.abort) return route.abort('failed');
      if (fault.status) return respond(fault.status, fault.data, fault.total);
    }
    if (pathname === '/api/auth/me') return respond(state.auth ? 200 : 401, state.auth ? { user: state.user } : { detail: 'Login required' });
    if (pathname === '/api/auth/login') { state.auth = true; return respond(200, { user: state.user }); }
    if (pathname === '/api/auth/logout') { state.auth = false; return respond(204); }
    if (!state.auth) return respond(401, { detail: 'Login required' });
    if (pathname === '/api/property-managers') {
      const offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 50);
      return respond(200, state.managers.slice(offset, offset + limit), state.managers.length);
    }
    if (pathname === '/api/rentals' && method === 'GET') {
      if (state.failList) return respond(503, { detail: 'Temporary list failure' });
      const query = (url.searchParams.get('q') || '').toLowerCase(), offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 50);
      const rows = state.records.filter((row) => `${row.listingTitle} ${row.propertyAddress}`.toLowerCase().includes(query)).sort((a, b) => a.id - b.id);
      return respond(200, rows.slice(offset, offset + limit), rows.length);
    }
    if (pathname === '/api/rentals' && method === 'POST') {
      const id = state.nextId++; const row = { ...fixture(id), ...body }; state.records.push(row);
      return respond(201, row);
    }
    const selected = pathname.match(/^\/api\/rentals\/(\d+)$/);
    if (selected) {
      const i = state.records.findIndex((row) => row.id === Number(selected[1]));
      if (i < 0) return respond(404, { detail: 'Rental not found' });
      if (method === 'GET') return respond(200, state.records[i]);
      if (method === 'PUT') { state.records[i] = { ...state.records[i], ...body }; return respond(200, state.records[i]); }
      if (method === 'DELETE') { state.records.splice(i, 1); return respond(204); }
    }
    return respond(404, { detail: 'Unknown mock route' });
  });
}
async function mockFlow(browser) {
  const state = { auth: false, records: Array.from({ length: 12 }, (_, i) => fixture(i + 1)), nextId: 801, requests: [], faults: [],
    managers: Array.from({ length: 101 }, (_, i) => ({ id: i + 1, name: `Manager ${i + 1}`, company: 'Browser Homes', email: `manager${i + 1}@example.com` })),
    user: { id: 1, name: 'Mock user', email: EMAIL } };
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 900 } });
  await mockRoutes(context, state); const page = await context.newPage(); page.setDefaultTimeout(15000);
  const errors = []; page.on('pageerror', (error) => errors.push(error.message));
  try {
    await check('Protected routes, login, paginated Home and obsolete shortcut removal', async () => {
      await page.goto(`${BASE}/create`); await page.getByRole('heading', { name: 'Login required' }).waitFor();
      assert.equal(await page.locator('article').count(), 0);
      await login(page); assert.deepEqual(await ids(page), [1,2,3,4,5,6,7,8,9,10]);
      await page.getByRole('button', { name: 'Next page' }).click();
      await card(page, 11).waitFor(); assert.deepEqual(await ids(page), [11,12]);
      assert.equal(await page.getByRole('button', { name: 'Next page' }).isDisabled(), true);
      assert.equal(await page.getByText(/Delete highest ID/).count(), 0);
      await page.getByLabel('Listings per page').selectOption('5'); await card(page, 1).waitFor();
      assert.deepEqual(await ids(page), [1,2,3,4,5]); return { total: 12, page_size: 5 };
    });
    await check('Empty, loading and recoverable list-error states', async () => {
      await search(page, 'nothing-matches'); await page.getByRole('heading', { name: 'No listings found' }).waitFor();
      state.failList = true; await page.getByLabel('Search listings').fill(''); await page.getByRole('button', { name: 'Search', exact: true }).click();
      await page.getByRole('alert').filter({ hasText: 'Temporary list failure' }).waitFor();
      assert.equal(await page.locator('article').count(), 0); state.failList = false;
      await page.getByRole('button', { name: 'Try again' }).click(); await home(page);
      const fault = { method: 'GET', path: '/api/rentals', gate: gate(), entered: gate() }; state.faults.push(fault);
      await page.getByRole('button', { name: 'Search', exact: true }).click(); await fault.entered.wait(`request entered: ${fault.method} ${fault.path}`);
      await page.getByText('Loading listings…', { exact: true }).waitFor(); fault.gate.resolve(); await home(page);
    });
    await check('Invalid and missing IDs show safe errors without mutation controls', async () => {
      for (const suffix of ['/update?id=bad', '/delete?id=-1', '/update']) {
        await page.goto(`${BASE}${suffix}`); await page.getByRole('heading', { name: 'Select a listing' }).waitFor();
        assert.equal(await page.getByRole('button', { name: /Save changes|Delete listing/ }).count(), 0);
      }
      await page.goto(`${BASE}/update?id=99999`); await page.getByRole('alert').filter({ hasText: 'Rental not found' }).waitFor();
    });
    await check('Manager failure recovers; no managers prevents saving', async () => {
      state.faults.push({ method: 'GET', path: '/api/property-managers', status: 503, data: { detail: 'Manager list unavailable' } });
      await page.goto(`${BASE}/create`); await page.getByRole('alert').filter({ hasText: 'Manager list unavailable' }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Add listing', exact: true }).isDisabled(), true);
      const managers = state.managers; state.managers = [];
      await page.getByRole('button', { name: 'Retry managers' }).click(); await page.getByRole('alert').filter({ hasText: 'No property managers are available' }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Add listing', exact: true }).isDisabled(), true);
      state.managers = managers; await page.reload();
    });
    const created = createFields('Mock Redux created', 101);
    await check('All manager pages load; invalid units/code/manager cannot submit', async () => {
      await page.getByRole('link', { name: 'Add listing', exact: true }).first().click(); await fill(page, created);
      assert.equal(await page.locator('[name=managerId] option').count(), 102);
      const before = state.requests.filter((r) => r.method === 'POST' && r.path === '/api/rentals').length;
      for (const [field, value] of [['availableUnits', '-1'], ['availableUnits', '1.5'], ['listingCode', 'bad'], ['managerId', '']]) {
        await fill(page, { ...created, listingCode: '' });
        if (field === 'managerId') await page.locator('[name=managerId]').selectOption(''); else await page.locator(`[name=${field}]`).fill(value);
        assert.equal(await page.locator('form').evaluate((form) => form.checkValidity()), false);
        await page.getByRole('button', { name: 'Add listing', exact: true }).click();
      }
      await fill(page, { ...created, listingCode: '' });
      assert.equal(state.requests.filter((r) => r.method === 'POST' && r.path === '/api/rentals').length, before);
    });
    await check('Write validation and network errors preserve local form input', async () => {
      state.faults.push({ method: 'POST', path: '/api/rentals', status: 422, data: { detail: [{ loc: ['body', 'listingCode'], msg: 'Mock rejected code' }] } });
      await page.getByRole('button', { name: 'Add listing', exact: true }).click(); await page.getByRole('alert').filter({ hasText: 'Mock rejected code' }).waitFor();
      state.faults.push({ method: 'POST', path: '/api/rentals', abort: true });
      await page.getByRole('button', { name: 'Add listing', exact: true }).click(); await page.getByRole('alert').filter({ hasText: 'Cannot reach' }).waitFor();
      assert.equal(await page.getByLabel('Listing title', { exact: true }).inputValue(), created.listingTitle);
    });
    await check('Synchronous double submit sends one write; failed refresh still shows success', async () => {
      const fault = { method: 'POST', path: '/api/rentals', gate: gate(), entered: gate() }; state.faults.push(fault);
      const before = state.requests.filter((r) => r.method === 'POST' && r.path === '/api/rentals').length;
      await page.locator('form').evaluate((form) => { form.requestSubmit(); form.requestSubmit(); });
      await fault.entered.wait(`request entered: ${fault.method} ${fault.path}`);
      assert.equal(await page.getByRole('button', { name: 'Saving…' }).isDisabled(), true);
      assert.equal(await page.getByRole('link', { name: 'Cancel', exact: true }).count(), 0);
      state.failList = true; fault.gate.resolve();
      await page.getByText('Listing added.', { exact: true }).waitFor();
      await page.getByRole('alert').filter({ hasText: 'Temporary list failure' }).waitFor();
      assert.equal(state.requests.filter((r) => r.method === 'POST' && r.path === '/api/rentals').length - before, 1);
      assert.equal(state.records.filter((row) => row.listingTitle === created.listingTitle).length, 1);
      await page.locator('[data-mutation-result]').filter({ hasText: created.listingTitle }).waitFor();
      state.failList = false; await page.getByRole('button', { name: 'Try again' }).click(); await home(page);
      await search(page, created.listingTitle); await card(page, 801).waitFor();
      return { server_assigned_id: 801, duplicate_write_count: 0 };
    });
    await check('Direct-ID update survives refresh and persists all HW5 fields', async () => {
      await card(page, 801).getByRole('link', { name: 'Update', exact: true }).click(); await page.reload();
      await page.getByRole('heading', { name: 'Update listing', exact: true }).waitFor();
      await fill(page, { listingTitle: 'Updated Redux rental', propertyAddress: '42 Revised Way', availableUnits: 0, managerId: 1, listingCode: 'S6102-R-9801' });
      state.faults.push({ method: 'PUT', path: '/api/rentals/801', status: 409, data: { detail: 'Listing code already exists' } });
      await page.getByRole('button', { name: 'Save changes', exact: true }).click();
      await page.getByRole('alert').filter({ hasText: 'Listing code already exists' }).waitFor();
      assert.equal(await page.getByLabel('Listing title', { exact: true }).inputValue(), 'Updated Redux rental');
      assert.equal(state.records.find((row) => row.id === 801).listingTitle, created.listingTitle);
      await page.getByRole('button', { name: 'Save changes', exact: true }).click(); await home(page); await search(page, 'Updated Redux rental');
      const row = state.records.find((row) => row.id === 801);
      assert.equal(row.availableUnits, 0); assert.equal(row.managerId, 1); assert.equal(row.description, created.description);
      assert.deepEqual(Object.keys(state.requests.filter((r) => r.method === 'PUT').at(-1).body).sort(), ['availableUnits','listingCode','listingTitle','managerId','propertyAddress']);
      await card(page, 801).waitFor();
    });
    await check('Per-row delete handles 204; narrow layout remains usable', async () => {
      await search(page, 'Updated Redux rental');
      state.faults.push({ method: 'DELETE', path: '/api/rentals/801', status: 409, data: { detail: 'Mock delete conflict' } });
      await card(page, 801).getByRole('button', { name: 'Delete', exact: true }).click();
      await card(page, 801).getByRole('alert').filter({ hasText: 'Mock delete conflict' }).waitFor();
      assert(state.records.some((row) => row.id === 801));
      const fault = { method: 'DELETE', path: '/api/rentals/801', gate: gate(), entered: gate() }; state.faults.push(fault);
      const before = state.requests.filter((row) => row.method === 'DELETE').length;
      await card(page, 801).getByRole('button', { name: 'Delete', exact: true }).evaluate((button) => { button.click(); button.click(); });
      await fault.entered.wait(`request entered: ${fault.method} ${fault.path}`); assert.equal(await card(page, 801).getByRole('button', { name: 'Deleting…' }).isDisabled(), true);
      assert.equal(state.requests.filter((row) => row.method === 'DELETE').length - before, 1); fault.gate.resolve();
      await page.getByText('Deleted listing #801', { exact: true }).waitFor(); await home(page);
      assert.equal(await page.getByText('Listing updated.', { exact: true }).count(), 0, 'Direct deletion must not retain an older update success notice');
      assert.equal(state.records.some((row) => row.id === 801), false);
      await page.setViewportSize({ width: 390, height: 844 }); await snapshot(page, 'mobile-home'); await page.setViewportSize({ width: 1280, height: 900 });
    });
    await check('Late detail cannot overwrite a newer selected listing', async () => {
      await search(page, ''); const fault = { method: 'GET', path: '/api/rentals/1', gate: gate(), entered: gate(), status: 200, data: fixture(1) }; state.faults.push(fault);
      await card(page, 1).getByRole('link', { name: 'Update', exact: true }).click(); await fault.entered.wait(`request entered: ${fault.method} ${fault.path}`);
      await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Home', exact: true }).click(); await home(page);
      await card(page, 2).getByRole('link', { name: 'Update', exact: true }).click(); await page.getByRole('heading', { name: 'Update listing', exact: true }).waitFor();
      fault.gate.resolve(); await delay(100);
      assert.equal(await page.getByLabel('Listing title', { exact: true }).inputValue(), fixture(2).listingTitle);
    });
    await check('Failed same-ID refresh removes the cached edit form', async () => {
      await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Home', exact: true }).click(); await home(page);
      const fault = { method: 'GET', path: '/api/rentals/2', gate: gate(), entered: gate(), status: 404, data: { detail: 'Rental no longer exists' } }; state.faults.push(fault);
      await card(page, 2).getByRole('link', { name: 'Update', exact: true }).click(); await fault.entered.wait('same-ID refresh entered');
      fault.gate.resolve(); await page.getByRole('alert').filter({ hasText: 'Rental no longer exists' }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Save changes', exact: true }).count(), 0);
    });
    await check('Late pre-mutation list cannot replace the post-mutation refresh', async () => {
      await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Add listing', exact: true }).click();
      await fill(page, createFields('Late successful rental'));
      const write = { method: 'POST', path: '/api/rentals', gate: gate(), entered: gate() }; state.faults.push(write);
      const validity = await page.locator('form').evaluate((form) => ({
        valid: form.checkValidity(), invalid: [...form.elements].filter((element) => !element.validity.valid).map((element) => ({ name: element.name, message: element.validationMessage })),
      }));
      assert.equal(validity.valid, true, JSON.stringify(validity));
      await page.getByRole('button', { name: 'Add listing', exact: true }).click();
      await write.entered.wait("create request entered before navigating Home");
      const oldTotal = state.records.length;
      const read = { method: 'GET', path: '/api/rentals', gate: gate(), entered: gate(), status: 200, data: state.records.slice(0,10), total: oldTotal }; state.faults.push(read);
      await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Home', exact: true }).click(); await read.entered.wait("pre-mutation Home list request entered");
      write.gate.resolve(); await home(page);
      assert.match(await page.locator('.result-count').innerText(), new RegExp(`^${oldTotal + 1} listings`));
      read.gate.resolve(); await delay(100);
      assert.match(await page.locator('.result-count').innerText(), new RegExp(`^${oldTotal + 1} listings`));
      await search(page, 'Late successful rental'); await card(page, 802).waitFor();
    });
    await check('New search results remain after an obsolete search response arrives', async () => {
      const fault = { method: 'GET', path: '/api/rentals', query: 'Quiet rental 1', gate: gate(), entered: gate(), status: 200, data: [fixture(1)], total: 1 }; state.faults.push(fault);
      await page.getByLabel('Search listings').fill('Quiet rental 1');
      await page.getByRole('button', { name: 'Search', exact: true }).click(); await fault.entered.wait('old search entered');
      await search(page, 'Late successful rental'); await card(page, 802).waitFor();
      fault.gate.resolve(); await delay(100); assert.deepEqual(await ids(page), [802]);
    });
    await check('Old-session 401 cannot expire a fresh login', async () => {
      await page.getByRole('link', { name: 'Add listing', exact: true }).first().click(); await fill(page, createFields('Old session write'));
      const fault = { method: 'POST', path: '/api/rentals', gate: gate(), entered: gate(), status: 401, data: { detail: 'Old session expired' } }; state.faults.push(fault);
      await page.getByRole('button', { name: 'Add listing', exact: true }).click(); await fault.entered.wait(`request entered: ${fault.method} ${fault.path}`);
      await page.getByRole('button', { name: 'Log out', exact: true }).click(); await page.waitForURL(`${BASE}/login`);
      await login(page, false); fault.gate.resolve(); await delay(100);
      assert.equal(new URL(page.url()).pathname, '/'); assert.equal(await page.getByRole('button', { name: 'Log out', exact: true }).count(), 1);
    });
    await check('Logout clears rentals and ignores an old-session successful write', async () => {
      await page.getByRole('link', { name: 'Add listing', exact: true }).first().click(); await fill(page, createFields('Stale success'));
      const fault = { method: 'POST', path: '/api/rentals', gate: gate(), entered: gate(), status: 201, data: { ...fixture(9901), listingTitle: 'Stale success' } }; state.faults.push(fault);
      await page.getByRole('button', { name: 'Add listing', exact: true }).click(); await fault.entered.wait(`request entered: ${fault.method} ${fault.path}`);
      await page.getByRole('button', { name: 'Log out', exact: true }).click(); await page.waitForURL(`${BASE}/login`);
      fault.gate.resolve(); await delay(100); assert.equal(await page.locator('article').count(), 0); assert.equal(new URL(page.url()).pathname, '/login');
      await login(page, false); assert.equal(await card(page, 9901).count(), 0);
    });
    await check('Current-session expiry clears visible records and blocks routes', async () => {
      state.auth = false; await page.getByRole('button', { name: 'Search', exact: true }).click();
      await page.waitForURL(`${BASE}/login`); await page.getByText(/Your session expired/).waitFor();
      assert.equal(await page.locator('article').count(), 0); assert.equal(await page.getByRole('button', { name: 'Log out', exact: true }).count(), 0);
      assert.deepEqual(errors, []);
    });
  } finally {
    report.requests = state.requests;
    for (const release of heldGates) release();
    await context.close();
  }
}
async function realFlow(browser) {
  assert(EMAIL && PASSWORD, 'Real mode requires private HW5/HW4_SEED_EMAIL and SEED_PASSWORD');
  assert(BASE.startsWith('https://'), 'Real Secure-cookie verification requires HTTPS');
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage(); page.setDefaultTimeout(15000);
  const run = `hw5-browser-${randomUUID()}`;
  const description = `Owned browser verification ${run}; bright quiet rental near campus.`;
  const owned = new Map(); let managerId; const errors = []; page.on('pageerror', (error) => errors.push(error.message));
  const journal = async () => fs.writeFile(path.resolve(RAW, 'real-browser-owned-fixtures.json'), JSON.stringify({ run, managerId, rentals: [...owned.keys()], description, submitterEmail: 'browser-owner@example.com' }, null, 2));
  try {
    await check('Real HTTPS login uses Secure HttpOnly cookie', async () => {
      await login(page); const cookie = (await context.cookies(BASE)).find((item) => item.name === 's6102_session');
      assert(cookie?.secure && cookie?.httpOnly); assert(!await page.evaluate(() => document.cookie.includes('s6102_session')));
      return { secure: cookie.secure, httpOnly: cookie.httpOnly, sameSite: cookie.sameSite };
    });
    const managerResponse = await context.request.post(`${BASE}/api/property-managers`, { data: { name: run, company: 'Browser Verification', email: `${run}@example.com` } });
    assert.equal(managerResponse.status(), 201); managerId = (await managerResponse.json()).id; await journal();
    await check('Real pagination matches API total and stable IDs', async () => {
      await search(page, ''); await page.getByLabel('Listings per page').selectOption('5');
      const firstResponse = await context.request.get(`${BASE}/api/rentals`, { params: { limit: 5, offset: 0 } });
      assert.equal(firstResponse.status(), 200); const total = Number(firstResponse.headers()['x-total-count']);
      assert(total > 5, 'Real pagination check requires at least six existing rentals in the owned acceptance database');
      const firstExpected = (await firstResponse.json()).map((row) => row.id);
      await page.getByText(`Page 1 of ${Math.ceil(total / 5)}`, { exact: true }).waitFor();
      const first = await ids(page); assert.deepEqual(first, firstExpected);
      await page.getByRole('button', { name: 'Next page' }).click(); await page.getByText(`Page 2 of ${Math.ceil(total / 5)}`, { exact: true }).waitFor();
      const second = await ids(page); assert(second.length > 0); assert(first.every((id) => id < second[0]));
      return { first, second, total, screenshot: await snapshot(page, 'home') };
    });
    let created;
    await check('UI create persists generated code, units and explicit manager', async () => {
      await page.getByRole('link', { name: 'Add listing', exact: true }).first().click();
      const values = { ...createFields(`${run} created`, managerId), description };
      await fill(page, values); await snapshot(page, 'create-form');
      const pending = page.waitForResponse(match('POST', '/api/rentals'));
      await page.getByRole('button', { name: 'Add listing', exact: true }).click(); const response = await pending;
      assert.equal(response.status(), 201); created = await response.json(); owned.set(created.id, created); await journal();
      assert.match(created.listingCode, /^S6102-R-[1-9][0-9]*$/); assert.equal(created.availableUnits, 2); assert.equal(created.managerId, managerId);
      await home(page); await page.locator('[data-mutation-result]').filter({ hasText: values.listingTitle }).waitFor();
      await search(page, values.listingTitle); await card(page, created.id).waitFor();
      const persisted = await context.request.get(`${BASE}/api/rentals/${created.id}`); assert.deepEqual(await persisted.json(), created);
      return { id: created.id, listingCode: created.listingCode, managerId, screenshot: await snapshot(page, 'created-home') };
    });
    await check('UI direct-ID update persists changed fields and preserves old fields', async () => {
      await page.goto(`${BASE}/update?id=${created.id}`); await page.reload();
      await page.getByRole('heading', { name: 'Update listing', exact: true }).waitFor();
      assert.equal(await page.getByLabel('Listing title', { exact: true }).inputValue(), created.listingTitle);
      await fill(page, { listingTitle: `${run} revised`, propertyAddress: '8702 Revised Browser Road', listingCode: created.listingCode, availableUnits: 0, managerId });
      await snapshot(page, 'update-form'); const pending = page.waitForResponse(match('PUT', `/api/rentals/${created.id}`));
      await page.getByRole('button', { name: 'Save changes', exact: true }).click(); const response = await pending; assert.equal(response.status(), 200);
      const changed = await response.json(); assert.equal(changed.availableUnits, 0); assert.equal(changed.description, description); assert.equal(changed.submitterEmail, created.submitterEmail);
      await home(page); await search(page, `${run} revised`); await card(page, created.id).waitFor(); await page.reload();
      await home(page); await search(page, `${run} revised`); await card(page, created.id).waitFor();
      return { id: created.id, preserved_original_fields: true, screenshot: await snapshot(page, 'updated-home') };
    });
    await check('Real empty result and responsive Home', async () => {
      await search(page, `${run}-no-match`); await page.getByRole('heading', { name: 'No listings found' }).waitFor();
      await search(page, `${run} revised`); await page.setViewportSize({ width: 390, height: 844 });
      const capture = await snapshot(page, 'mobile-home'); await page.setViewportSize({ width: 1280, height: 900 }); return capture;
    });
    await check('UI per-row delete returns 204 and remains absent after reload', async () => {
      await card(page, created.id).getByRole('link', { name: 'Review deletion', exact: true }).click(); await page.reload();
      await page.getByRole('heading', { name: 'Delete listing', exact: true }).waitFor(); await snapshot(page, 'delete-confirmation');
      await page.getByRole('link', { name: 'Cancel', exact: true }).click(); await home(page); await search(page, `${run} revised`);
      const pending = page.waitForResponse(match('DELETE', `/api/rentals/${created.id}`));
      await card(page, created.id).getByRole('button', { name: 'Delete', exact: true }).click(); assert.equal((await pending).status(), 204);
      await page.getByText(`Deleted listing #${created.id}`, { exact: true }).waitFor();
      owned.delete(created.id); await journal(); await home(page); await page.reload(); await home(page);
      assert.equal((await context.request.get(`${BASE}/api/rentals/${created.id}`)).status(), 404);
      return { deleted_id: created.id, screenshot: await snapshot(page, 'deleted-home') };
    });
    await check('Real logout clears visible data and API access', async () => {
      await page.getByRole('button', { name: 'Log out', exact: true }).click(); await page.waitForURL(`${BASE}/login`);
      assert.equal(await page.locator('article').count(), 0); assert.equal((await context.request.get(`${BASE}/api/rentals`)).status(), 401);
      assert.deepEqual(errors, []);
    });
  } finally {
    const cleanup = []; report.cleanup = cleanup;
    try {
      assert.equal((await context.request.post(`${BASE}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })).status(), 200);
      // Search the unique run marker too, recovering any committed create whose response was lost.
      const response = await context.request.get(`${BASE}/api/rentals`, { params: { q: run, limit: 100 } });
      if (response.status() === 200) for (const row of await response.json()) owned.set(row.id, row);
      for (const id of owned.keys()) {
        const current = await context.request.get(`${BASE}/api/rentals/${id}`);
        if (current.status() === 404) continue;
        assert.equal(current.status(), 200); const row = await current.json();
        assert.equal(row.description, description, 'Cleanup must match the unique ownership marker');
        assert.equal(row.submitterEmail, 'browser-owner@example.com');
        const removed = await context.request.delete(`${BASE}/api/rentals/${id}`); assert.equal(removed.status(), 204); cleanup.push({ rental_id: id, status: 204 });
      }
      if (managerId) {
        const current = await context.request.get(`${BASE}/api/property-managers/${managerId}`); assert.equal(current.status(), 200);
        assert.equal((await current.json()).name, run);
        const removed = await context.request.delete(`${BASE}/api/property-managers/${managerId}`); assert.equal(removed.status(), 204); cleanup.push({ manager_id: managerId, status: 204 });
      }
      await context.request.post(`${BASE}/api/auth/logout`);
    } catch (error) { report.cleanup_error = redact(error.stack); throw error; }
    finally { await context.close(); }
  }
}
async function main() {
  assert(RAW && path.isAbsolute(RAW), 'HW5_RAW_DIR must be an explicit absolute selected-evidence or external scratch directory');
  if (SHOTS) { assert(path.isAbsolute(SHOTS)); await fs.mkdir(SHOTS, { recursive: true }); }
  await fs.mkdir(RAW, { recursive: true });
  report.git_revision = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: ROOT, encoding: 'utf8' }).trim();
  report.source_sha256 = {};
  async function hash(filename) {
    if ((await fs.stat(filename)).isDirectory()) { for (const child of (await fs.readdir(filename)).sort()) await hash(path.join(filename, child)); }
    else report.source_sha256[path.relative(ROOT, filename)] = createHash('sha256').update(await fs.readFile(filename)).digest('hex');
  }
  for (const name of ['frontend/src', 'frontend/package.json', 'frontend/package-lock.json', 'tests/browser_hw05_part1.cjs']) await hash(path.join(ROOT, name));
  let browser;
  try { browser = await chromium.launch({ headless: true }); await (MODE === 'mock' ? mockFlow : realFlow)(browser); report.status = 'pass'; }
  catch (error) { report.status = 'fail'; report.error = redact(error.stack); console.error(report.error); process.exitCode = 1; }
  finally {
    if (browser) await browser.close(); report.finished_at = now();
    report.passed_checks = report.checks.filter((check) => check.status === 'pass').length;
    report.failed_checks = report.checks.filter((check) => check.status === 'fail').length;
    const filename = path.resolve(RAW, `${MODE}-browser.json`); await fs.writeFile(filename, `${redact(JSON.stringify(report, null, 2))}\n`);
    console.log(`Evidence: ${filename} (${report.status})`);
  }
}
main().catch((error) => { console.error(redact(error.stack)); process.exitCode = 1; });
