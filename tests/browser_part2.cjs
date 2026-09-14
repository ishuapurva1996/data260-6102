// Run with npm run test:browser after installing the web Python requirements,
// npm dependencies, and Chromium (npx playwright install chromium).
// Each run owns a temporary server and in-memory store, separate from port 8702.
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const net = require('node:net');
const path = require('node:path');
const { chromium, request } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const PYTHON = process.env.PYTHON || path.join(ROOT, '.venv-web', 'bin', 'python');
const SCREENSHOTS = process.env.PART2_SCREENSHOT_DIR;
const FIXTURES = [
  {
    listingTitle: 'Cedar Sanctuary',
    propertyAddress: '10 Willow Lane, San Jose, CA',
    submitterEmail: 'cedar@example.com',
    description: 'A bright apartment with a quiet study and secure bicycle storage.',
    propertyType: 'apartment',
    termsAccepted: true,
  },
  {
    listingTitle: 'Bay Room',
    propertyAddress: '99 Cedar Road, San Jose, CA',
    submitterEmail: 'bay@example.com',
    description: 'A comfortable house with a garden and a covered parking space.',
    propertyType: 'house',
    termsAccepted: true,
  },
];

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function freePort() {
  const socket = net.createServer();
  await new Promise((resolve, reject) => {
    socket.once('error', reject);
    socket.listen(0, '127.0.0.1', resolve);
  });
  const { port } = socket.address();
  await new Promise((resolve, reject) => socket.close((error) => error ? reject(error) : resolve()));
  return port;
}

async function main() {
  const port = await freePort();
  const baseURL = `http://127.0.0.1:${port}`;
  const server = spawn(PYTHON, [
    '-m', 'uvicorn', 'main:app', '--app-dir', path.join(ROOT, 'code', 'web_application'),
    '--host', '127.0.0.1', '--port', String(port),
  ], { cwd: ROOT, env: { ...process.env, PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let serverOutput = '';
  let serverError;
  for (const stream of [server.stdout, server.stderr]) {
    stream.on('data', (chunk) => { serverOutput = (serverOutput + chunk).slice(-12000); });
  }
  server.on('error', (error) => { serverError = error; });
  let browser;
  let api;
  const failures = [];
  let passed = 0;

  try {
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt += 1) {
      if (serverError) throw serverError;
      if (server.exitCode !== null) throw new Error(`Test server exited before startup:\n${serverOutput}`);
      try {
        ready = (await fetch(`${baseURL}/api/rentals`, { signal: AbortSignal.timeout(500) })).ok;
      } catch { /* The socket is not listening yet. */ }
      if (ready) break;
      await delay(100);
    }
    assert(ready, `Test server did not become ready:\n${serverOutput}`);
    browser = await chromium.launch({ headless: true });
    api = await request.newContext({ baseURL });
    if (SCREENSHOTS) await fs.mkdir(SCREENSHOTS, { recursive: true });

    async function rentals() {
      const response = await api.get('/api/rentals');
      assert.equal(response.status(), 200);
      return response.json();
    }

    async function reset(extra = []) {
      for (const rental of await rentals()) {
        assert.equal((await api.delete(`/api/rentals/${rental.id}`)).status(), 204);
      }
      for (const data of [...FIXTURES, ...extra]) {
        assert.equal((await api.post('/api/rentals', { data })).status(), 201);
      }
    }

    async function visibleIDs(page) {
      return page.locator('#rentalList li[data-id]').evaluateAll((rows) => rows.map((row) => Number(row.dataset.id)));
    }

    async function waitForIDs(page, ids) {
      await page.waitForFunction((expected) => {
        const actual = [...document.querySelectorAll('#rentalList li[data-id]')].map((row) => Number(row.dataset.id));
        return JSON.stringify(actual) === JSON.stringify(expected);
      }, ids);
    }

    async function open(page, suffix = '/') {
      await page.goto(`${baseURL}${suffix}`);
      await waitForIDs(page, (await rentals()).map((rental) => rental.id));
    }

    async function fillCreate(page, overrides = {}) {
      const data = { ...FIXTURES[0], listingTitle: 'New Campus Apartment', ...overrides };
      for (const name of ['listingTitle', 'propertyAddress', 'submitterEmail', 'description']) {
        await page.locator(`#${name}`).fill(data[name]);
      }
      await page.locator('#propertyType').selectOption(data.propertyType);
      await page.locator('#termsAccepted').setChecked(data.termsAccepted);
      return data;
    }

    async function navigateWith(page, action) {
      await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }), action()]);
      assert.equal(new URL(page.url()).pathname, '/');
      assert.equal(new URL(page.url()).search, '');
      await waitForIDs(page, (await rentals()).map((rental) => rental.id));
    }

    async function search(page, value, ids) {
      await page.locator('#searchQuery').fill(value);
      await Promise.all([
        page.waitForResponse((response) => {
          const url = new URL(response.url());
          return url.pathname === '/api/rentals' && (url.searchParams.get('q') || '') === value.trim()
            && response.request().method() === 'GET';
        }),
        page.locator('#searchButton').click(),
      ]);
      await waitForIDs(page, ids);
    }

    async function edit(page, id) {
      await page.getByRole('button', { name: `Edit listing ID ${id}`, exact: true }).click();
      assert.equal(await page.locator('#updateForm').isVisible(), true);
      assert.equal(await page.locator('#updateHeading').innerText(), `Edit Listing ID ${id}`);
      assert.equal(await page.locator('#updateButton').innerText(), 'Save changes');
      assert.equal(await page.locator('#cancelEditButton').innerText(), 'Cancel');
    }

    async function noOverflow(page) {
      const sizes = await page.evaluate(() => ({
        viewport: window.innerWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth,
      }));
      assert(sizes.document <= sizes.viewport && sizes.body <= sizes.viewport, JSON.stringify(sizes));
    }

    async function screenshot(page, name) {
      if (SCREENSHOTS) await page.screenshot({ path: path.join(SCREENSHOTS, `${name}.png`), fullPage: true });
    }

    async function test(name, run, { fixtures = true, width = 375 } = {}) {
      if (fixtures) await reset();
      const page = await browser.newPage({ viewport: { width, height: 812 } });
      page.setDefaultTimeout(12000);
      const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      page.on('console', (message) => {
        // Failed requests are deliberately exercised below; Chromium reports them
        // as console errors even when the application handles them correctly.
        if (message.type() === 'error' && !/Failed to load resource|net::ERR_|Failed to fetch/.test(message.text())) {
          errors.push(message.text());
        }
      });
      try {
        await run(page);
        assert.deepEqual(errors, [], 'Unexpected browser errors');
        passed += 1;
        console.log(`PASS ${name}`);
      } catch (error) {
        failures.push(name);
        console.error(`FAIL ${name}\n${error.stack || error}`);
        await screenshot(page, `failure-${failures.length}`).catch(() => {});
      } finally {
        await page.close();
      }
    }

    await test('seeded list and usable 375px layout', async (page) => {
      assert.deepEqual((await rentals()).map((rental) => rental.id), [1, 2]);
      await open(page);
      assert.equal(await page.locator('#updateForm').isHidden(), true);
      assert.equal(await page.getByRole('button', { name: 'Edit listing ID 2', exact: true }).isEnabled(), true);
      await noOverflow(page);
      await screenshot(page, 'mobile-seeded-list');
    }, { fixtures: false });

    await test('create uses the API and survives reload', async (page) => {
      await open(page);
      const data = await fillCreate(page);
      await navigateWith(page, () => page.locator('#submitButton').click());
      assert.deepEqual((await rentals()).find((rental) => rental.id === 3), { id: 3, ...data });
      await page.reload();
      await waitForIDs(page, [1, 2, 3]);
      assert((await page.locator('#rental-3').innerText()).includes(data.listingTitle));
      await noOverflow(page);
    });

    for (const id of [1, 2]) {
      await test(`Edit prefills ID ${id} and updates only its title and address`, async (page) => {
        const before = await rentals();
        const original = before.find((rental) => rental.id === id);
        await open(page);
        await edit(page, id);
        assert.equal(await page.locator('#updateTitle').inputValue(), original.listingTitle);
        assert.equal(await page.locator('#updateAddress').inputValue(), original.propertyAddress);
        const changes = { listingTitle: `Updated Rental ${id}`, propertyAddress: '6102 University Avenue, San Jose' };
        await page.locator('#updateTitle').fill(changes.listingTitle);
        await page.locator('#updateAddress').fill(changes.propertyAddress);
        const saved = page.waitForRequest((req) => req.method() === 'PUT');
        await navigateWith(page, () => page.locator('#updateButton').click());
        const request = await saved;
        assert.equal(new URL(request.url()).pathname, `/api/rentals/${id}`);
        assert.deepEqual(request.postDataJSON(), changes);
        assert.deepEqual(await rentals(), before.map((rental) => rental.id === id ? { ...rental, ...changes } : rental));
        assert.equal(await page.locator('#updateForm').isHidden(), true);
      });
    }

    await test('Cancel discards a draft without a request and restores focus', async (page) => {
      await open(page);
      const before = await rentals();
      let writes = 0;
      page.on('request', (req) => { if (['PUT', 'POST', 'DELETE'].includes(req.method())) writes += 1; });
      await edit(page, 2);
      await page.locator('#updateTitle').fill('Unsaved title');
      await page.locator('#updateAddress').fill('Unsaved address');
      await page.locator('#cancelEditButton').click();
      assert.equal(await page.locator('#updateForm').isHidden(), true);
      assert.equal(await page.getByRole('button', { name: 'Edit listing ID 2', exact: true }).evaluate((el) => el === document.activeElement), true);
      await edit(page, 2);
      assert.equal(await page.locator('#updateTitle').inputValue(), before[1].listingTitle);
      assert.equal(await page.locator('#updateAddress').inputValue(), before[1].propertyAddress);
      assert.equal(writes, 0);
      assert.deepEqual(await rentals(), before);
    });

    await test('Cancel focuses search during a pending or failed list refresh', async (page) => {
      await open(page);
      await edit(page, 2);
      let release;
      const pending = new Promise((resolve) => { release = resolve; });
      await page.route('**/api/rentals', async (route) => {
        await pending;
        await route.continue();
      });
      await page.locator('#clearSearchButton').click();
      try {
        assert.equal(await page.getByRole('button', { name: 'Edit listing ID 2', exact: true }).isDisabled(), true);
        await page.locator('#cancelEditButton').click();
        assert.equal(await page.locator('#updateForm').isHidden(), true);
        assert.equal(await page.locator('#searchQuery').evaluate((el) => el === document.activeElement), true);
      } finally {
        release();
      }
      await page.waitForFunction(() => document.querySelector('#searchForm').getAttribute('aria-busy') === 'false');
      await page.unroute('**/api/rentals');
      await edit(page, 2);
      await page.route('**/api/rentals', (route) => route.abort('failed'));
      await page.locator('#clearSearchButton').click();
      await page.locator('#retryButton').waitFor({ state: 'visible' });
      assert.equal(await page.getByRole('button', { name: 'Edit listing ID 2', exact: true }).isDisabled(), true);
      await page.locator('#cancelEditButton').click();
      assert.equal(await page.locator('#updateForm').isHidden(), true);
      assert.equal(await page.locator('#searchQuery').evaluate((el) => el === document.activeElement), true);
    });

    await test('same-record Edit preserves drafts and changing targets confirms discard', async (page) => {
      await open(page);
      await edit(page, 1);
      await page.locator('#updateTitle').fill('Unsaved ID 1 title');
      let dialogs = 0;
      page.on('dialog', () => { dialogs += 1; });
      await edit(page, 1);
      assert.equal(await page.locator('#updateTitle').inputValue(), 'Unsaved ID 1 title');
      assert.equal(dialogs, 0, 'Reopening the same record should not ask to discard');
      page.once('dialog', (dialog) => dialog.dismiss());
      await page.getByRole('button', { name: 'Edit listing ID 2', exact: true }).click();
      assert.equal(await page.locator('#updateHeading').innerText(), 'Edit Listing ID 1');
      assert.equal(await page.locator('#updateTitle').inputValue(), 'Unsaved ID 1 title');
      page.once('dialog', (dialog) => dialog.accept());
      await edit(page, 2);
      assert.equal(await page.locator('#updateTitle').inputValue(), FIXTURES[1].listingTitle);
      assert.equal(await page.locator('#updateAddress').inputValue(), FIXTURES[1].propertyAddress);
      assert.equal(dialogs, 2);
      assert.deepEqual(await rentals(), FIXTURES.map((rental, index) => ({ id: index + 1, ...rental })));
    });

    await test('search may hide the edited row without changing its draft or target', async (page) => {
      await open(page);
      await edit(page, 2);
      await page.locator('#updateTitle').fill('Filtered-out draft');
      await search(page, 'Willow', [1]);
      assert.equal(await page.locator('#updateHeading').innerText(), 'Edit Listing ID 2');
      assert.equal(await page.locator('#updateTitle').inputValue(), 'Filtered-out draft');
      assert.equal(await page.locator('#updateButton').isEnabled(), true);
      await noOverflow(page);
      await screenshot(page, 'mobile-edit-filtered-out-listing');
      await navigateWith(page, () => page.locator('#updateButton').click());
      assert.equal((await rentals())[1].listingTitle, 'Filtered-out draft');
      assert.equal((await rentals())[0].listingTitle, FIXTURES[0].listingTitle);
    });

    await test('a failed update preserves the selected record and draft for retry', async (page) => {
      await open(page);
      await edit(page, 2);
      await page.locator('#updateTitle').fill('Retry rental');
      await page.locator('#updateAddress').fill('42 Retry Road');
      const before = await rentals();
      await page.route('**/api/rentals/2', (route) => route.abort('failed'));
      await page.locator('#updateButton').click();
      await page.waitForFunction(() => !document.querySelector('#updateButton').disabled);
      assert.match(await page.locator('#updateStatus').innerText(), /error|fail|could not|couldn't|unable|connect/i);
      assert.equal(await page.locator('#updateHeading').innerText(), 'Edit Listing ID 2');
      assert.equal(await page.locator('#updateTitle').inputValue(), 'Retry rental');
      assert.equal(await page.locator('#updateAddress').inputValue(), '42 Retry Road');
      assert.deepEqual(await rentals(), before);
      await page.unroute('**/api/rentals/2');
      await navigateWith(page, () => page.locator('#updateButton').click());
      assert.deepEqual((await rentals())[1], { ...before[1], listingTitle: 'Retry rental', propertyAddress: '42 Retry Road' });
    });

    await test('a deleted selected record reports 404, retains the draft, and permits Cancel', async (page) => {
      await open(page);
      await edit(page, 2);
      await page.locator('#updateTitle').fill('Draft for removed listing');
      assert.equal((await api.delete('/api/rentals/2')).status(), 204);
      const failed = page.waitForResponse((response) => response.request().method() === 'PUT');
      await page.locator('#updateButton').click();
      assert.equal((await failed).status(), 404);
      await page.waitForFunction(() => document.querySelector('#updateStatus').textContent.trim().length > 0
        && !document.querySelector('#cancelEditButton').disabled);
      assert.match(await page.locator('#updateStatus').innerText(), /not found|unavailable|not available|no longer|does not exist/i);
      assert.equal(await page.locator('#updateHeading').innerText(), 'Edit Listing ID 2');
      assert.equal(await page.locator('#updateTitle').inputValue(), 'Draft for removed listing');
      await search(page, 'Willow', [1]);
      assert.equal(await page.locator('#updateButton').isDisabled(), true);
      assert.match(await page.locator('#updateForm').innerText(), /not found|unavailable|not available|no longer|does not exist/i);
      await page.locator('#cancelEditButton').click();
      assert.equal(await page.locator('#updateForm').isHidden(), true);
      assert.equal(await page.locator('#searchQuery').evaluate((el) => el === document.activeElement), true);
      assert.deepEqual((await rentals()).map((rental) => rental.id), [1]);
    });

    await test('pending update disables competing actions and sends only one PUT', async (page) => {
      await open(page);
      await edit(page, 2);
      await page.locator('#updateTitle').fill('One saved update');
      let release;
      let captured;
      let writes = 0;
      const started = new Promise((resolve) => { captured = resolve; });
      await page.route('**/api/rentals/2', async (route) => {
        writes += 1;
        captured();
        await new Promise((resolve) => { release = resolve; });
        await route.continue();
      });
      await page.locator('#updateButton').click();
      await Promise.race([started, delay(5000).then(() => { throw new Error('Update was not sent'); })]);
      try {
        for (const id of ['updateTitle', 'updateAddress', 'updateButton', 'cancelEditButton', 'submitButton', 'searchButton', 'deleteHighestButton']) {
          assert.equal(await page.locator(`#${id}`).isDisabled(), true, `${id} should lock while saving`);
        }
        for (const button of await page.locator('#rentalList button').all()) assert.equal(await button.isDisabled(), true);
        await page.locator('#updateForm').evaluate((form) => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
        assert.equal(writes, 1);
        await noOverflow(page);
      } finally {
        await navigateWith(page, async () => { release(); });
      }
      assert.equal(writes, 1);
      assert.equal((await rentals())[1].listingTitle, 'One saved update');
    });

    await test('search matches either field, ignores case, and clears', async (page) => {
      await open(page);
      await search(page, ' cEdAr ', [1, 2]);
      await search(page, 'Willow', [1]);
      await search(page, 'BAY ROOM', [2]);
      await search(page, 'no-such-listing', []);
      assert.equal(await page.locator('#emptyState').isVisible(), true);
      assert.match(await page.locator('#emptyState').innerText(), /match|search/i);
      assert.equal(await page.locator('#deleteHighestButton').isEnabled(), true);
      await screenshot(page, 'mobile-no-search-matches');
      await page.locator('#clearSearchButton').click();
      await waitForIDs(page, [1, 2]);
      assert.equal(await page.locator('#searchQuery').inputValue(), '');
      await search(page, 'Willow', [1]);
      await search(page, '   ', [1, 2]);
    });

    await test('highest-ID deletion is global when search hides the highest record', async (page) => {
      await reset([{ ...FIXTURES[0], listingTitle: 'Hidden Highest Rental' }]);
      await open(page);
      await search(page, 'Willow', [1, 3]);
      await search(page, 'Sanctuary', [1]);
      assert.match(await page.locator('#deleteHighestButton').innerText(), /\b3\b/);
      page.once('dialog', (dialog) => dialog.accept());
      await navigateWith(page, () => page.locator('#deleteHighestButton').click());
      assert.deepEqual((await rentals()).map((rental) => rental.id), [1, 2]);
      await search(page, 'no-such-listing', []);
      assert.match(await page.locator('#deleteHighestButton').innerText(), /\b2\b/);
      page.once('dialog', (dialog) => dialog.accept());
      await navigateWith(page, () => page.locator('#deleteHighestButton').click());
      assert.deepEqual((await rentals()).map((rental) => rental.id), [1]);
    });

    await test('row deletion can be cancelled, accepts 204, and ID 2 remains editable without ID 1', async (page) => {
      await open(page);
      page.once('dialog', (dialog) => dialog.dismiss());
      await page.getByRole('button', { name: 'Delete listing ID 1', exact: true }).click();
      assert.deepEqual((await rentals()).map((rental) => rental.id), [1, 2]);
      page.once('dialog', (dialog) => dialog.accept());
      await navigateWith(page, () => page.getByRole('button', { name: 'Delete listing ID 1', exact: true }).click());
      assert.equal(await page.locator('#updateForm').isHidden(), true);
      await edit(page, 2);
      await page.locator('#updateTitle').fill('Still editable without ID 1');
      await navigateWith(page, () => page.locator('#updateButton').click());
      assert.equal((await rentals())[0].listingTitle, 'Still editable without ID 1');
      page.once('dialog', (dialog) => dialog.accept());
      await navigateWith(page, () => page.locator('#deleteHighestButton').click());
      assert.deepEqual(await rentals(), []);
      assert.equal(await page.locator('#deleteHighestButton').isDisabled(), true);
      assert.equal(await page.locator('#emptyState').isVisible(), true);
      assert.match(await page.locator('#emptyState').innerText(), /first|no rental|no listing/i);
      await screenshot(page, 'mobile-empty-store');
    });

    await test('loading locks editing and duplicate submissions create only one record', async (page) => {
      await open(page, '/?slowSave=true');
      await edit(page, 1);
      await fillCreate(page);
      let createRequests = 0;
      page.on('request', (req) => {
        if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/rentals') createRequests += 1;
      });
      const navigation = page.waitForNavigation({ waitUntil: 'domcontentloaded' });
      await page.locator('#submitButton').click();
      for (const id of ['listingTitle', 'propertyAddress', 'submitterEmail', 'description', 'propertyType',
        'termsAccepted', 'submitButton', 'updateTitle', 'updateAddress', 'updateButton', 'cancelEditButton']) {
        assert.equal(await page.locator(`#${id}`).isDisabled(), true, `${id} should be disabled while saving`);
      }
      assert.match(await page.locator('#formStatus').innerText(), /saving|creat|loading/i);
      await page.locator('#rentalForm').evaluate((form) => {
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      });
      assert.equal(createRequests, 0, 'Slow-save aid should wait before sending the real request');
      await noOverflow(page);
      await screenshot(page, 'mobile-loading');
      await navigation;
      await waitForIDs(page, [1, 2, 3]);
      assert.equal(createRequests, 1);
      assert.equal((await rentals()).length, 3);
    });

    await test('simulated create error keeps input and makes no backend changes', async (page) => {
      await open(page, '/?simulateError=true');
      const data = await fillCreate(page);
      let createRequests = 0;
      page.on('request', (req) => { if (req.method() === 'POST') createRequests += 1; });
      await page.locator('#submitButton').click();
      await page.waitForFunction(() => !document.querySelector('#submitButton').disabled);
      assert.match(await page.locator('#formStatus').innerText(), /error|fail|could not|couldn't|unable/i);
      assert.equal(await page.locator('#listingTitle').inputValue(), data.listingTitle);
      assert.equal(await page.locator('#termsAccepted').isChecked(), true);
      assert.equal(createRequests, 0);
      assert.equal((await rentals()).length, 2);
      await screenshot(page, 'mobile-simulated-error');
    });

    await test('real network failure retains the form and allows retry', async (page) => {
      await open(page);
      const data = await fillCreate(page);
      await page.route('**/api/rentals', async (route) => {
        if (route.request().method() === 'POST') await route.abort('failed');
        else await route.continue();
      });
      await page.locator('#submitButton').click();
      await page.waitForFunction(() => !document.querySelector('#submitButton').disabled);
      assert.match(await page.locator('#formStatus').innerText(), /error|fail|could not|couldn't|unable|connect/i);
      assert.equal(await page.locator('#listingTitle').inputValue(), data.listingTitle);
      assert.equal((await rentals()).length, 2);
      await page.unroute('**/api/rentals');
      await navigateWith(page, () => page.locator('#submitButton').click());
      assert.equal((await rentals()).length, 3);
    });

    await test('initial list failure offers a working retry', async (page) => {
      await page.route('**/api/rentals', (route) => route.abort('failed'));
      await page.goto(baseURL);
      await page.locator('#retryButton').waitFor({ state: 'visible' });
      assert.match(await page.locator('#listStatus').innerText(), /error|fail|could not|couldn't|unable|connect/i);
      await page.unroute('**/api/rentals');
      await page.locator('#retryButton').click();
      await waitForIDs(page, [1, 2]);
    });

    await test('FastAPI validation arrays display readable messages', async (page) => {
      await open(page);
      await fillCreate(page);
      await page.route('**/api/rentals', async (route) => {
        if (route.request().method() !== 'POST') return route.continue();
        await route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({ detail: [{ loc: ['body', 'listingTitle'], msg: 'Use a nonblank title.', type: 'value_error' }] }),
        });
      });
      await page.locator('#submitButton').click();
      await page.waitForFunction(() => !document.querySelector('#submitButton').disabled);
      const text = await page.locator('#formStatus').innerText();
      assert.match(text, /Use a nonblank title\./);
      assert.doesNotMatch(text, /\[object Object\]/);
      assert.equal((await rentals()).length, 2);
    });

    await test('a delayed search cannot overwrite a later Clear action', async (page) => {
      await open(page);
      const all = await rentals();
      let release;
      let captured;
      let finished;
      const requestCaptured = new Promise((resolve) => { captured = resolve; });
      const requestFinished = new Promise((resolve) => { finished = resolve; });
      const isDelayed = (req) => new URL(req.url()).searchParams.get('q') === 'Sanctuary';
      page.on('requestfinished', (req) => { if (isDelayed(req)) finished(); });
      page.on('requestfailed', (req) => { if (isDelayed(req)) finished(); });
      await page.route('**/api/rentals?*', async (route) => {
        if (!isDelayed(route.request())) return route.continue();
        captured();
        await new Promise((resolve) => { release = resolve; });
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([all[0]]) }).catch(() => {});
      });
      await page.locator('#searchQuery').fill('Sanctuary');
      await page.locator('#searchButton').click();
      await Promise.race([requestCaptured, delay(5000).then(() => { throw new Error('Search request was not sent'); })]);
      await page.locator('#clearSearchButton').click();
      await waitForIDs(page, [1, 2]);
      release();
      await Promise.race([requestFinished, delay(5000).then(() => { throw new Error('Delayed search did not settle'); })]);
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.deepEqual(await visibleIDs(page), [1, 2]);
      assert.equal(await page.locator('#searchQuery').inputValue(), '');
    });

    await test('user markup is literal text and long content fits mobile', async (page) => {
      const data = {
        ...FIXTURES[0],
        listingTitle: '<img src=x onerror="window.__injected=1">',
        propertyAddress: 'A'.repeat(180),
        description: '<script>window.__injected=2</script> with enough description characters.',
      };
      assert.equal((await api.post('/api/rentals', { data })).status(), 201);
      await open(page);
      const row = page.locator('#rental-3');
      assert.match(await row.innerText(), /<img src=x onerror=/);
      assert.equal(await row.locator('img,script').count(), 0);
      assert.equal(await page.evaluate(() => window.__injected), undefined);
      await noOverflow(page);
      await screenshot(page, 'mobile-long-literal-content');
    });

    await test('desktop list and forms remain usable', async (page) => {
      await open(page);
      await edit(page, 2);
      for (const id of ['rentalForm', 'updateForm', 'searchForm', 'rentalList']) {
        assert.equal(await page.locator(`#${id}`).isVisible(), true);
      }
      await noOverflow(page);
      await screenshot(page, 'desktop-seeded-list');
    }, { width: 1280 });

    console.log(`\n${passed} browser checks passed; ${failures.length} failed.`);
    if (failures.length) throw new Error(`Browser checks failed: ${failures.join('; ')}`);
  } finally {
    if (api) await api.dispose();
    if (browser) await browser.close();
    if (server.exitCode === null && !serverError) {
      const stopped = new Promise((resolve) => server.once('exit', resolve));
      server.kill('SIGTERM');
      await Promise.race([stopped, delay(3000)]);
      if (server.exitCode === null) server.kill('SIGKILL');
    }
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
