#!/usr/bin/env node
// Uses an already running server; never starts/stops a process or seeds a database.
// MOCK: HW4_BASE_URL=http://localhost:5173 node tests/browser_hw04_part1.cjs --mock
// REAL: supply HW4_SEED_EMAIL/HW4_SEED_PASSWORD outside tracked source, then run --real.
// Optional real restart handshake: set HW4_RESTART_READY_FILE and
// HW4_RESTART_DONE_FILE to unused temporary paths. The owner restarts its server
// after READY exists and writes DONE only once the restarted server is ready.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const MODE = process.argv.includes('--mock') ? 'mock' : process.argv.includes('--expiry') ? 'expiry' : 'real';
const BASE = (process.env.HW4_BASE_URL || (MODE === 'mock' ? 'http://localhost:5173' : 'https://localhost:8702')).replace(/\/$/, '');
const RAW = path.resolve(process.env.HW4_RAW_DIR || path.join(ROOT, 'reports/hw04/raw/part1'));
const SHOTS = path.resolve(process.env.HW4_SCREENSHOTS_DIR || path.join(ROOT, 'reports/hw04/screenshots/part1'));
const EMAIL = MODE === 'mock' ? 'browser@example.invalid' : process.env.HW4_SEED_EMAIL;
const PASSWORD = MODE === 'mock' ? 'mock-password-not-a-real-credential' : process.env.HW4_SEED_PASSWORD;
const CREATE_KEYS = ['description', 'listingTitle', 'propertyAddress', 'propertyType', 'submitterEmail', 'termsAccepted'];
const UPDATE_KEYS = ['listingTitle', 'propertyAddress'];
const secrets = new Set([PASSWORD].filter(Boolean));
const now = () => new Date().toISOString();
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const relative = (filename) => path.relative(ROOT, filename).split(path.sep).join('/');
const evidence = {
  schema_version: 1, mode: MODE.toUpperCase(), started_at: now(), status: 'running',
  command: `node tests/browser_hw04_part1.cjs --${MODE}`,
  base_url: BASE, cwd: ROOT, checks: [], screenshots: [], requests: [],
  limitations: MODE === 'mock'
    ? ['MOCK ONLY: intercepted HTTP responses validate React behavior, not authentication security, MySQL storage, or final port 8702.']
    : ['The owner supplies the running HTTPS/MySQL service and credentials. The runner never resets a database.', 'Idle expiry is captured separately by --expiry against an explicitly configured short-timeout service.'],
};

function redact(value) {
  let safe = String(value);
  for (const secret of secrets) safe = safe.split(secret).join('[REDACTED]');
  return safe.replace(/(s6102_session=)[^;\s]+/gi, '$1[REDACTED]');
}

async function check(name, action, page) {
  const result = { name, status: 'running', started_at: now() };
  evidence.checks.push(result);
  try {
    result.details = await action();
    result.status = 'pass';
    console.log(`PASS [${MODE.toUpperCase()}] ${name}`);
    return result.details;
  } catch (error) {
    result.status = 'fail';
    result.error = redact(error.stack || error);
    throw error;
  } finally {
    result.finished_at = now();
    if (page && !page.isClosed()) result.actual_url = page.url();
  }
}

async function snapshot(page, name) {
  await page.evaluate(() => document.fonts.ready);
  if (MODE === 'mock') {
    await page.evaluate(() => {
      let marker = document.querySelector('[data-hw4-mock-evidence]');
      if (!marker) {
        marker = document.createElement('div');
        marker.setAttribute('data-hw4-mock-evidence', 'true');
        marker.textContent = 'MOCK TEST — API responses intercepted by Playwright';
        marker.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:#562300;color:#fff;padding:6px 10px;font:12px sans-serif;z-index:2147483647;pointer-events:none;text-align:center';
        document.body.append(marker);
      }
    });
  }
  const dimensions = await page.evaluate(() => ({
    viewport_width: innerWidth, document_width: document.documentElement.scrollWidth,
    body_width: document.body.scrollWidth, document_height: document.documentElement.scrollHeight, scroll_y: scrollY,
  }));
  assert(dimensions.document_width <= dimensions.viewport_width, `Document overflows: ${JSON.stringify(dimensions)}`);
  assert(dimensions.body_width <= dimensions.viewport_width, `Body overflows: ${JSON.stringify(dimensions)}`);
  const filename = path.join(SHOTS, `${MODE}-${name}.png`);
  await page.screenshot({
    path: filename, fullPage: dimensions.document_height <= 6000, animations: 'disabled',
    mask: [page.locator('input[type="password"]')], maskColor: '#dbe4d9',
  });
  const capture = { file: relative(filename), mode: MODE.toUpperCase(), captured_at: now(), actual_url: page.url(), viewport: page.viewportSize(), full_page: dimensions.document_height <= 6000, dimensions };
  evidence.screenshots.push(capture);
  return capture;
}

function requestMatch(method, pathname) {
  return (value) => value.request().method() === method && new URL(value.url()).pathname === pathname;
}

async function waitHome(page) {
  await page.waitForURL(`${BASE}/`);
  await page.getByRole('heading', { name: 'Rental listings', exact: true }).waitFor();
  await page.locator('.result-count').waitFor();
}

async function login(page, password = PASSWORD) {
  await page.goto(`${BASE}/login`);
  await page.getByLabel('Email', { exact: true }).fill(EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(password);
  const response = page.waitForResponse(requestMatch('POST', '/api/auth/login'));
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  return response;
}

async function fillRental(page, values) {
  await page.getByLabel('Listing title', { exact: true }).fill(values.listingTitle);
  await page.getByLabel('Property address', { exact: true }).fill(values.propertyAddress);
  if (Object.hasOwn(values, 'submitterEmail')) {
    await page.getByLabel('Landlord Email', { exact: true }).fill(values.submitterEmail);
    await page.getByLabel('Description', { exact: true }).fill(values.description);
    await page.getByLabel('Property type', { exact: true }).selectOption(values.propertyType);
    await page.getByLabel('I accept the terms', { exact: true }).check();
  }
}

async function assertValues(page, values) {
  assert.equal(await page.getByLabel('Listing title', { exact: true }).inputValue(), values.listingTitle);
  assert.equal(await page.getByLabel('Property address', { exact: true }).inputValue(), values.propertyAddress);
  if (Object.hasOwn(values, 'submitterEmail')) {
    assert.equal(await page.getByLabel('Landlord Email', { exact: true }).inputValue(), values.submitterEmail);
    assert.equal(await page.getByLabel('Description', { exact: true }).inputValue(), values.description);
    assert.equal(await page.getByLabel('Property type', { exact: true }).inputValue(), values.propertyType);
    assert.equal(await page.getByLabel('I accept the terms', { exact: true }).isChecked(), true);
  }
}

const cardFor = (page, title) => page.getByRole('article').filter({ hasText: title });
const fixture = (id = 17) => ({
  id, listingTitle: `Quiet apartment ${id}`, propertyAddress: `${id} Browser Test Lane`,
  submitterEmail: 'landlord@example.com', description: 'A spacious apartment with a sunny living room and quiet study area.',
  propertyType: 'apartment', termsAccepted: true,
});

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

async function installMock(context, state) {
  await context.route(url => url.pathname.startsWith('/api/'), async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const pathname = url.pathname;
    const body = method === 'GET' ? undefined : request.postDataJSON();
    const entry = { method, path: pathname, query: url.search, at: now() };
    // Authentication bodies and cookies never enter evidence.
    if (pathname.startsWith('/api/rentals') && body !== null) entry.body = body;
    state.requests.push(entry);
    const respond = async (status, payload) => {
      entry.status = status;
      if (status === 204) return route.fulfill({ status, body: '' });
      return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });
    };
    const faultIndex = state.faults.findIndex((fault) => fault.method === method && fault.path === pathname);
    if (faultIndex >= 0) {
      const fault = state.faults.splice(faultIndex, 1)[0];
      if (fault.gate) {
        fault.entered.resolve();
        await fault.gate.promise;
      }
      if (fault.abort) { entry.status = 'network-abort'; return route.abort('failed'); }
      if (fault.status) return respond(fault.status, fault.payload);
    }
    if (pathname === '/api/auth/me') return respond(state.auth ? 200 : 401, state.auth ? { user: state.user } : { detail: 'Login required' });
    if (pathname === '/api/auth/login') {
      if (body?.email !== EMAIL || body?.password !== PASSWORD) return respond(401, { detail: 'Invalid email or password' });
      state.auth = true;
      return respond(200, { user: state.user });
    }
    if (pathname === '/api/auth/logout') { state.auth = false; return respond(204); }
    if (!state.auth) return respond(401, { detail: 'Login required' });
    if (pathname === '/api/rentals' && method === 'GET') {
      const query = (url.searchParams.get('q') || '').toLowerCase();
      return respond(200, state.records.filter((row) => `${row.listingTitle} ${row.propertyAddress}`.toLowerCase().includes(query)));
    }
    if (pathname === '/api/rentals' && method === 'POST') {
      const record = { id: state.nextId++, ...body };
      state.records.push(record);
      return respond(201, record);
    }
    const match = pathname.match(/^\/api\/rentals\/(\d+)$/);
    if (match) {
      const index = state.records.findIndex((row) => row.id === Number(match[1]));
      if (index < 0) return respond(404, { detail: 'Rental not found' });
      if (method === 'GET') return respond(200, state.records[index]);
      if (method === 'PUT') {
        state.records[index] = { ...state.records[index], ...body };
        return respond(200, state.records[index]);
      }
      if (method === 'DELETE') { state.records.splice(index, 1); return respond(204); }
    }
    return respond(404, { detail: 'Not found' });
  });
}

async function signedOutRoutes(page) {
  for (const suffix of ['/', '/create', '/update?id=17', '/delete?id=17']) {
    await page.goto(`${BASE}${suffix}`);
    await page.getByText(/Login required/).waitFor();
    assert.equal(await page.getByRole('article').count(), 0, `Protected records exposed at ${suffix}`);
    assert.equal(await page.getByRole('button', { name: 'Add listing', exact: true }).count(), 0);
  }
  return snapshot(page, 'signed-out');
}

async function selectionErrors(page) {
  const checked = [];
  for (const suffix of ['/update', '/delete', '/update?id=invalid', '/delete?id=-1']) {
    await page.goto(`${BASE}${suffix}`);
    await page.getByRole('alert').waitFor();
    assert.equal(await page.getByRole('button', { name: /^(Save changes|Delete listing)$/ }).count(), 0);
    checked.push({ path: suffix, message: await page.getByRole('alert').innerText() });
  }
  return checked;
}

async function mockFlow(browser) {
  const state = {
    auth: false, records: [fixture()], nextId: 9317, faults: [], requests: [],
    user: { id: 1, name: 'Mock browser user', email: EMAIL },
  };
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await installMock(context, state);
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(redact(error.message)));
  try {
    await check('Signed-out protected routes hide records and mutations', () => signedOutRoutes(page), page);
    await check('Invalid login remains rejected; valid login loads records', async () => {
      const invalid = await login(page, 'invalid-mock-password');
      assert.equal(invalid.status(), 401);
      await page.getByRole('alert').waitFor();
      await snapshot(page, 'invalid-login');
      const valid = await login(page);
      assert.equal(valid.status(), 200);
      await waitHome(page);
      await cardFor(page, fixture().listingTitle).waitFor();
      return snapshot(page, 'home');
    }, page);
    await check('Empty authenticated listing state', async () => {
      state.records = [];
      await page.reload();
      await waitHome(page);
      await page.getByText(/no (rental )?listings/i).waitFor();
      return snapshot(page, 'empty');
    }, page);
    await check('Missing or invalid selected IDs show a safe error', async () => {
      const from = state.requests.length;
      const result = await selectionErrors(page);
      assert.equal(state.requests.slice(from).filter((item) => /^\/api\/rentals\//.test(item.path)).length, 0);
      return result;
    }, page);
    await check('Missing server record reports 404 safely', async () => {
      await page.goto(`${BASE}/update?id=99999`);
      await page.getByRole('alert').waitFor();
      assert.equal(await page.getByRole('button', { name: 'Save changes', exact: true }).count(), 0);
      return snapshot(page, 'missing-record');
    }, page);

    const created = { ...fixture(), listingTitle: 'Mock contract test listing', propertyAddress: '9317 Contract Avenue' };
    delete created.id;
    await check('422 validation detail preserves all create values', async () => {
      await page.goto(`${BASE}/create`);
      await page.getByRole('heading', { name: 'Add a rental listing', exact: true }).waitFor();
      await fillRental(page, created);
      state.faults.push({ method: 'POST', path: '/api/rentals', status: 422, payload: { detail: [{ loc: ['body', 'listingTitle'], msg: 'Title rejected by mock validation', type: 'value_error' }] } });
      await page.getByRole('button', { name: 'Add listing', exact: true }).click();
      await page.getByRole('alert').filter({ hasText: 'Title rejected by mock validation' }).waitFor();
      await assertValues(page, created);
      assert.equal(new URL(page.url()).pathname, '/create');
      return snapshot(page, 'create-validation');
    }, page);
    await check('Network failure retains input and never reports success', async () => {
      state.faults.push({ method: 'POST', path: '/api/rentals', abort: true });
      await page.getByRole('button', { name: 'Add listing', exact: true }).click();
      await page.getByRole('alert').filter({ hasText: /network|connect|reach|fetch/i }).waitFor();
      await assertValues(page, created);
      assert.equal(new URL(page.url()).pathname, '/create');
      assert.equal(state.records.length, 0);
      return snapshot(page, 'network-error');
    }, page);
    await check('Pending submit sends one six-field create; home uses server ID', async () => {
      const gate = deferred();
      const entered = deferred();
      state.faults.push({ method: 'POST', path: '/api/rentals', gate, entered });
      const before = state.requests.filter((item) => item.method === 'POST' && item.path === '/api/rentals').length;
      await page.getByRole('button', { name: 'Add listing', exact: true }).click();
      await entered.promise;
      try {
        // Two dispatched submits bypass button disabling and exercise the handler guard.
        await page.locator('form').evaluate((form) => {
          form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
          form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        });
        await delay(100);
        assert.equal(state.requests.filter((item) => item.method === 'POST' && item.path === '/api/rentals').length - before, 1);
        assert.equal(await page.locator('form button[type="submit"]').isDisabled(), true);
        await snapshot(page, 'create-pending');
      } finally { gate.resolve(); }
      await waitHome(page);
      const row = state.records.find((record) => record.listingTitle === created.listingTitle);
      assert.equal(row.id, 9317);
      const request = state.requests.filter((item) => item.method === 'POST' && item.path === '/api/rentals').at(-1);
      assert.deepEqual(Object.keys(request.body).sort(), CREATE_KEYS);
      assert.deepEqual(request.body, created);
      await cardFor(page, created.listingTitle).waitFor();
      assert.match(await cardFor(page, created.listingTitle).innerText(), /9317/);
      return { sent_body: request.body, server_id: row.id, screenshot: await snapshot(page, 'created-home') };
    }, page);
    const update = { listingTitle: 'Updated mock listing', propertyAddress: '42 Revised Avenue' };
    await check('Update deep link survives refresh and sends only two fields', async () => {
      await cardFor(page, created.listingTitle).getByRole('link', { name: 'Update', exact: true }).click();
      await page.waitForURL(`${BASE}/update?id=9317`);
      await page.reload();
      await page.getByRole('heading', { name: 'Update listing', exact: true }).waitFor();
      await assertValues(page, { listingTitle: created.listingTitle, propertyAddress: created.propertyAddress });
      await fillRental(page, update);
      await snapshot(page, 'update-form');
      await page.getByRole('button', { name: 'Save changes', exact: true }).click();
      await waitHome(page);
      await cardFor(page, update.listingTitle).waitFor();
      const request = state.requests.filter((item) => item.method === 'PUT').at(-1);
      assert.equal(request.path, '/api/rentals/9317');
      assert.deepEqual(Object.keys(request.body).sort(), UPDATE_KEYS);
      assert.deepEqual(request.body, update);
      assert.equal(state.records[0].description, created.description);
      return { sent_body: request.body, screenshot: await snapshot(page, 'updated-home') };
    }, page);
    await check('Route change ignores an obsolete detail response', async () => {
      const gate = deferred();
      const entered = deferred();
      state.faults.push({ method: 'GET', path: '/api/rentals/9317', gate, entered });
      await cardFor(page, update.listingTitle).getByRole('link', { name: 'Update', exact: true }).click();
      await entered.promise;
      await page.goBack();
      await waitHome(page);
      gate.resolve();
      await delay(150);
      await waitHome(page);
      assert.equal(await page.getByRole('heading', { name: 'Update listing', exact: true }).count(), 0);
      return { obsolete_record_id: 9317, route_after_delayed_response: new URL(page.url()).pathname };
    }, page);
    await check('Narrow viewport supports required record screens', async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      await snapshot(page, 'mobile-home');
      for (const [suffix, heading, name] of [
        ['/create', 'Add a rental listing', 'mobile-create'],
        ['/update?id=9317', 'Update listing', 'mobile-update'],
        ['/delete?id=9317', 'Delete listing', 'mobile-delete'],
      ]) {
        await page.goto(`${BASE}${suffix}`);
        await page.getByRole('heading', { name: heading, exact: true }).waitFor();
        if (suffix.startsWith('/update')) await assertValues(page, update);
        if (suffix.startsWith('/delete')) await page.getByText(update.listingTitle, { exact: true }).waitFor();
        await snapshot(page, name);
      }
      await page.setViewportSize({ width: 1280, height: 900 });
      return { viewport: { width: 390, height: 844 }, screenshots: 4 };
    }, page);
    await check('Delete confirmation supports Cancel and empty 204 success', async () => {
      await page.goto(`${BASE}/delete?id=9317`);
      await page.getByRole('heading', { name: 'Delete listing', exact: true }).waitFor();
      await page.getByText(update.listingTitle, { exact: true }).waitFor();
      await page.getByRole('link', { name: 'Cancel', exact: true }).or(page.getByRole('button', { name: 'Cancel', exact: true })).click();
      await waitHome(page);
      assert.equal(state.records.length, 1);
      await cardFor(page, update.listingTitle).getByRole('link', { name: 'Delete', exact: true }).click();
      await page.getByText(update.propertyAddress, { exact: true }).waitFor();
      await snapshot(page, 'delete-confirmation');
      await page.getByRole('button', { name: 'Delete listing', exact: true }).click();
      await waitHome(page);
      await page.getByText(/no (rental )?listings/i).waitFor();
      assert.equal(state.records.length, 0);
      const request = state.requests.filter((item) => item.method === 'DELETE').at(-1);
      assert.equal(request.path, '/api/rentals/9317');
      assert.equal(request.status, 204);
      return { response_status: 204, response_body: '', screenshot: await snapshot(page, 'deleted-home') };
    }, page);
    await check('401 during mutation clears stale authenticated interface', async () => {
      await page.goto(`${BASE}/create`);
      await fillRental(page, created);
      state.auth = false;
      await page.getByRole('button', { name: 'Add listing', exact: true }).click();
      await page.waitForURL(`${BASE}/login`);
      await page.getByRole('button', { name: 'Log in', exact: true }).waitFor();
      assert.equal(await page.getByRole('article').count(), 0);
      assert.equal(await page.getByRole('button', { name: 'Log out', exact: true }).count(), 0);
      return snapshot(page, 'session-expired');
    }, page);
    await check('Refresh checks the server identity; logout rejects later navigation', async () => {
      await login(page);
      await waitHome(page);
      const before = state.requests.filter((item) => item.path === '/api/auth/me').length;
      await page.reload();
      await waitHome(page);
      assert(state.requests.filter((item) => item.path === '/api/auth/me').length > before);
      await page.getByRole('button', { name: 'Log out', exact: true }).click();
      await page.getByText(/Login required/).waitFor();
      assert.equal(state.auth, false);
      return { identity_rechecked: true, logout_status: state.requests.findLast((item) => item.path === '/api/auth/logout').status };
    }, page);
    await check('No uncaught browser JavaScript errors', async () => { assert.deepEqual(errors, []); return { uncaught_errors: errors }; }, page);
  } finally {
    evidence.requests = state.requests;
    await context.close();
  }
}

async function restartCheckpoint(page, id, title) {
  const ready = process.env.HW4_RESTART_READY_FILE;
  const done = process.env.HW4_RESTART_DONE_FILE;
  if (!ready && !done) {
    evidence.limitations.push('Backend restart persistence was not requested for this run; use the optional READY/DONE handshake for that separate check.');
    return;
  }
  assert(ready && done, 'Both restart handshake paths are required');
  await assert.rejects(fs.access(done), 'Restart DONE path must not already exist');
  await fs.writeFile(ready, JSON.stringify({ ready_at: now(), record_id: id, base_url: BASE }, null, 2), { flag: 'wx' });
  console.log(`RESTART READY: ${ready}`);
  const started = Date.now();
  for (;;) {
    try { await fs.access(done); break; } catch { /* Owner has not acknowledged its completed restart. */ }
    if (Date.now() - started > 120000) throw new Error('Owner did not acknowledge restart within 120 seconds');
    await delay(250);
  }
  await page.reload();
  await waitHome(page);
  await cardFor(page, title).waitFor();
  const stored = await page.context().request.get(`${BASE}/api/rentals/${id}`);
  assert.equal(stored.status(), 200, 'Stored authentication session and created rental must survive restart');
  assert.equal((await stored.json()).listingTitle, title);
  return { record_id: id, restart_acknowledged: true, session_survived: true, screenshot: await snapshot(page, 'after-backend-restart') };
}

async function realFlow(browser) {
  assert(EMAIL && PASSWORD, 'Real mode requires HW4_SEED_EMAIL and HW4_SEED_PASSWORD supplied outside tracked source');
  assert.equal(new URL(BASE).protocol, 'https:', 'Real mode requires HTTPS for the Secure session cookie');
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(redact(error.message)));
  let createdId;
  const created = { ...fixture(), listingTitle: `HW4 browser verification ${Date.now()}`, propertyAddress: '6102 Verification Avenue' };
  delete created.id;
  try {
    await check('Signed-out direct visits hide protected records', () => signedOutRoutes(page), page);
    await check('Unauthenticated CRUD APIs reject requests; unknown API remains JSON', async () => {
      const outcomes = [];
      for (const [method, suffix, data] of [
        ['get', '/api/rentals'], ['get', '/api/rentals/1'], ['post', '/api/rentals', created],
        ['put', '/api/rentals/1', { listingTitle: 'Unauthorized test', propertyAddress: 'Denied address' }], ['delete', '/api/rentals/1'],
      ]) {
        const response = await context.request[method](`${BASE}${suffix}`, data ? { data } : {});
        assert.equal(response.status(), 401, `${method.toUpperCase()} ${suffix}`);
        outcomes.push({ method: method.toUpperCase(), path: suffix, status: response.status() });
      }
      const unknown = await context.request.get(`${BASE}/api/this-route-does-not-exist`);
      assert.equal(unknown.status(), 404);
      assert.match(unknown.headers()['content-type'], /application\/json/);
      return { unauthenticated: outcomes, unknown_api: { status: unknown.status(), content_type: unknown.headers()['content-type'] } };
    }, page);
    await check('Invalid credentials stay rejected', async () => {
      const response = await login(page, 'known-invalid-browser-test-password');
      assert.equal(response.status(), 401);
      await page.getByRole('alert').waitFor();
      assert.equal((await context.cookies(BASE)).some((cookie) => cookie.name === 's6102_session'), false);
      return { response_status: response.status(), screenshot: await snapshot(page, 'invalid-login') };
    }, page);
    await check('Valid HTTPS login sets an opaque HTTP-only secure cookie', async () => {
      const response = await login(page);
      assert.equal(response.status(), 200);
      await waitHome(page);
      const cookie = (await context.cookies(BASE)).find((item) => item.name === 's6102_session');
      assert(cookie, 'Login must set s6102_session');
      secrets.add(cookie.value);
      assert.equal(cookie.httpOnly, true);
      assert.equal(cookie.secure, true);
      assert.equal(cookie.sameSite, 'Lax');
      assert.equal(cookie.path, '/');
      assert.equal(await page.evaluate(() => document.cookie.includes('s6102_session=')), false);
      const leaked = await page.evaluate((token) => {
        const stored = [...Object.values(localStorage), ...Object.values(sessionStorage)];
        return stored.some((value) => value.includes(token));
      }, cookie.value);
      assert.equal(leaked, false, 'Session cookie must not be copied into browser storage');
      const setCookies = (await response.headersArray()).filter((header) => header.name.toLowerCase() === 'set-cookie').map((header) => ({ name: header.name, value: header.value.replace(/^([^=]+=)[^;]*/, '$1[REDACTED]') }));
      return { status: response.status(), cookie: { name: cookie.name, value: '[REDACTED]', httpOnly: cookie.httpOnly, secure: cookie.secure, sameSite: cookie.sameSite, path: cookie.path }, captured_set_cookie_headers: setCookies, javascript_cannot_read_cookie: true, screenshot: await snapshot(page, 'authenticated-home') };
    }, page);
    await check('Create sends six fields and renders the database-assigned ID', async () => {
      await page.getByRole('link', { name: 'Add listing', exact: true }).first().click();
      await page.getByRole('heading', { name: 'Add a rental listing', exact: true }).waitFor();
      await fillRental(page, created);
      await snapshot(page, 'create-form');
      const pending = page.waitForResponse(requestMatch('POST', '/api/rentals'));
      await page.getByRole('button', { name: 'Add listing', exact: true }).click();
      const response = await pending;
      assert.equal(response.status(), 201);
      const body = response.request().postDataJSON();
      assert.deepEqual(Object.keys(body).sort(), CREATE_KEYS);
      assert.deepEqual(body, created);
      const record = await response.json();
      assert(Number.isSafeInteger(record.id) && record.id > 0);
      createdId = record.id;
      await waitHome(page);
      await cardFor(page, created.listingTitle).waitFor();
      await cardFor(page, created.listingTitle).scrollIntoViewIfNeeded();
      assert((await cardFor(page, created.listingTitle).innerText()).includes(String(createdId)));
      evidence.requests.push({ method: 'POST', path: '/api/rentals', body, status: response.status(), returned_id: createdId });
      return { server_id: createdId, sent_body: body, status: response.status(), screenshot: await snapshot(page, 'created-home') };
    }, page);
    const update = { listingTitle: `${created.listingTitle} revised`, propertyAddress: '8702 Persistent Record Road' };
    await check('Update direct URL and refresh retain selection; two fields persist', async () => {
      await page.goto(`${BASE}/update?id=${createdId}`);
      await page.reload();
      await page.getByRole('heading', { name: 'Update listing', exact: true }).waitFor();
      await assertValues(page, { listingTitle: created.listingTitle, propertyAddress: created.propertyAddress });
      await fillRental(page, update);
      await snapshot(page, 'update-form');
      const pending = page.waitForResponse(requestMatch('PUT', `/api/rentals/${createdId}`));
      await page.getByRole('button', { name: 'Save changes', exact: true }).click();
      const response = await pending;
      assert.equal(response.status(), 200);
      const body = response.request().postDataJSON();
      assert.deepEqual(Object.keys(body).sort(), UPDATE_KEYS);
      assert.deepEqual(body, update);
      const record = await response.json();
      for (const field of ['description', 'submitterEmail', 'propertyType', 'termsAccepted']) assert.equal(record[field], created[field]);
      await waitHome(page);
      await page.reload();
      await cardFor(page, update.listingTitle).waitFor();
      await cardFor(page, update.listingTitle).scrollIntoViewIfNeeded();
      evidence.requests.push({ method: 'PUT', path: `/api/rentals/${createdId}`, body, status: response.status() });
      return { sent_body: body, unchanged_extra_fields: true, screenshot: await snapshot(page, 'updated-home') };
    }, page);
    if (process.env.HW4_RESTART_READY_FILE || process.env.HW4_RESTART_DONE_FILE) {
      await check('Updated rental and authentication survive owner-controlled backend restart', () => restartCheckpoint(page, createdId, update.listingTitle), page);
    } else {
      evidence.limitations.push('Backend restart was not exercised in this run. Use the documented READY/DONE handshake to capture it.');
    }
    await check('Real missing/invalid ID routes remain safe', () => selectionErrors(page), page);
    await check('Narrow real browser shows persisted records without horizontal overflow', async () => {
      await page.goto(BASE);
      await waitHome(page);
      await cardFor(page, update.listingTitle).waitFor();
      await page.setViewportSize({ width: 390, height: 844 });
      const capture = await snapshot(page, 'mobile-home');
      await page.setViewportSize({ width: 1280, height: 900 });
      return capture;
    }, page);
    await check('Delete direct URL confirms selected record, then handles empty 204', async () => {
      await page.goto(`${BASE}/delete?id=${createdId}`);
      await page.reload();
      await page.getByRole('heading', { name: 'Delete listing', exact: true }).waitFor();
      await page.getByText(update.listingTitle, { exact: true }).waitFor();
      await page.getByText(update.propertyAddress, { exact: true }).waitFor();
      await snapshot(page, 'delete-confirmation');
      const pending = page.waitForResponse(requestMatch('DELETE', `/api/rentals/${createdId}`));
      await page.getByRole('button', { name: 'Delete listing', exact: true }).click();
      const response = await pending;
      assert.equal(response.status(), 204);
      assert(['0', undefined].includes(response.headers()['content-length']), '204 must not advertise a response body');
      await waitHome(page);
      await page.reload();
      await waitHome(page);
      assert.equal(await cardFor(page, update.listingTitle).count(), 0);
      const missing = await context.request.get(`${BASE}/api/rentals/${createdId}`);
      assert.equal(missing.status(), 404);
      evidence.requests.push({ method: 'DELETE', path: `/api/rentals/${createdId}`, status: response.status() });
      const deletedId = createdId;
      createdId = undefined;
      return { deleted_id: deletedId, response_status: 204, response_body: '204 No Content (status/header check)', subsequent_get_status: missing.status(), screenshot: await snapshot(page, 'deleted-home') };
    }, page);
    await check('Logout clears cookie and blocks protected routes again', async () => {
      const pending = page.waitForResponse(requestMatch('POST', '/api/auth/logout'));
      await page.getByRole('button', { name: 'Log out', exact: true }).click();
      assert.equal((await pending).status(), 204);
      await page.getByText(/Login required/).waitFor();
      assert.equal((await context.cookies(BASE)).some((cookie) => cookie.name === 's6102_session'), false);
      const denied = await context.request.get(`${BASE}/api/rentals`);
      assert.equal(denied.status(), 401);
      await page.goto(`${BASE}/create`);
      await page.getByText(/Login required/).waitFor();
      return { api_after_logout: denied.status(), screenshot: await snapshot(page, 'after-logout') };
    }, page);
    await check('No uncaught browser JavaScript errors', async () => { assert.deepEqual(errors, []); return { uncaught_errors: errors }; }, page);
  } finally {
    // Only remove this runner's own row if a later assertion failed.
    if (createdId !== undefined) {
      try {
        const result = await context.request.delete(`${BASE}/api/rentals/${createdId}`);
        evidence.failure_cleanup = { record_id: createdId, delete_status: result.status() };
      } catch (error) { evidence.failure_cleanup = { record_id: createdId, error: redact(error.message) }; }
    }
    await context.close();
  }
}

// Run only against the owner's explicit 2-second idle-timeout test process.
async function expiryFlow(browser) {
  assert(EMAIL && PASSWORD, 'Expiry mode requires private seed credentials');
  assert.equal(process.env.HW4_EXPIRY_TEST, '2', 'Confirm the service uses the 2-second test seam');
  evidence.limitations = ['Real HTTPS/MySQL with create_app(idle_timeout=2) test seam; production retains 300-second idle and 3600-second absolute lifetime.'];
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  try {
    await check('Real login before controlled idle expiry', async () => {
      assert.equal((await login(page)).status(), 200);
      await waitHome(page);
      await page.getByRole('article').first().waitFor();
      return { idle_timeout_seconds: 2, screenshot: await snapshot(page, 'before-idle') };
    }, page);
    await check('Expired MySQL session clears records and returns to login', async () => {
      await delay(3200);
      const response = page.waitForResponse(requestMatch('GET', '/api/rentals'));
      await page.getByRole('button', { name: 'Search', exact: true }).click();
      assert.equal((await response).status(), 401);
      await page.waitForURL(`${BASE}/login`);
      await page.getByText(/session expired/).waitFor();
      assert.equal(await page.getByRole('article').count(), 0);
      assert.equal(await page.getByRole('button', { name: 'Log out', exact: true }).count(), 0);
      return { status: 401, records_cleared: true, screenshot: await snapshot(page, 'session-expired') };
    }, page);
  } finally { await context.close(); }
}

async function sourceMetadata() {
  try { evidence.git_revision = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: ROOT, encoding: 'utf8' }).trim(); }
  catch { evidence.git_revision = 'unavailable'; }
  evidence.source_sha256 = {};
  async function walk(filename) {
    let stat;
    try { stat = await fs.stat(filename); } catch (error) { if (error.code === 'ENOENT') return; throw error; }
    if (stat.isDirectory()) {
      for (const entry of (await fs.readdir(filename)).sort()) await walk(path.join(filename, entry));
    } else if (stat.isFile()) {
      evidence.source_sha256[relative(filename)] = createHash('sha256').update(await fs.readFile(filename)).digest('hex');
    }
  }
  for (const filename of ['frontend/src', 'frontend/package.json', 'frontend/package-lock.json', 'frontend/vite.config.js', 'tests/browser_hw04_part1.cjs', 'tests/browser_hw04_part1_runtime.py']) await walk(path.join(ROOT, filename));
}

async function main() {
  assert(!process.argv.includes('--mock') || !process.argv.includes('--real'), 'Choose one of --mock or --real');
  await fs.mkdir(RAW, { recursive: true });
  await fs.mkdir(SHOTS, { recursive: true });
  await sourceMetadata();
  let browser;
  try {
    if (MODE === 'real') assert(EMAIL && PASSWORD, 'Real mode requires HW4_SEED_EMAIL and HW4_SEED_PASSWORD supplied outside tracked source');
    browser = await chromium.launch({ headless: true });
    if (MODE === 'mock') await mockFlow(browser);
    else if (MODE === 'expiry') await expiryFlow(browser);
    else await realFlow(browser);
    evidence.status = 'pass';
  } catch (error) {
    evidence.status = 'fail';
    evidence.error = redact(error.stack || error);
    process.exitCode = 1;
    console.error(evidence.error);
  } finally {
    if (browser) await browser.close();
    evidence.finished_at = now();
    evidence.passed_checks = evidence.checks.filter((item) => item.status === 'pass').length;
    evidence.failed_checks = evidence.checks.filter((item) => item.status === 'fail').length;
    const filename = path.join(RAW, `${MODE}-browser.json`);
    await fs.writeFile(filename, `${redact(JSON.stringify(evidence, null, 2))}\n`);
    console.log(`Evidence: ${relative(filename)} (${evidence.status})`);
  }
}

main().catch((error) => { console.error(redact(error.stack || error)); process.exitCode = 1; });
