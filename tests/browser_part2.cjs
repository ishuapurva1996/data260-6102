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
      assert.equal(await page.locator('#updateButton').isEnabled(), true);
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

    await test('update changes only the title and address of ID 1', async (page) => {
      const before = await rentals();
      await open(page);
      await page.locator('#updateTitle').fill('Updated First Rental');
      await page.locator('#updateAddress').fill('6102 University Avenue, San Jose');
      await navigateWith(page, () => page.locator('#updateButton').click());
      const after = await rentals();
      assert.deepEqual(after[0], {
        ...before[0], listingTitle: 'Updated First Rental', propertyAddress: '6102 University Avenue, San Jose',
      });
      assert.deepEqual(after[1], before[1]);
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

    await test('row deletion can be cancelled, accepts 204, and disables missing ID 1 update', async (page) => {
      await open(page);
      page.once('dialog', (dialog) => dialog.dismiss());
      await page.getByRole('button', { name: 'Delete listing ID 1', exact: true }).click();
      assert.deepEqual((await rentals()).map((rental) => rental.id), [1, 2]);
      page.once('dialog', (dialog) => dialog.accept());
      await navigateWith(page, () => page.getByRole('button', { name: 'Delete listing ID 1', exact: true }).click());
      assert.equal(await page.locator('#updateButton').isDisabled(), true);
      assert.match(await page.locator('#updateForm').innerText(), /ID 1 is not available/i);
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
      await fillCreate(page);
      let createRequests = 0;
      page.on('request', (req) => {
        if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/rentals') createRequests += 1;
      });
      const navigation = page.waitForNavigation({ waitUntil: 'domcontentloaded' });
      await page.locator('#submitButton').click();
      for (const id of ['listingTitle', 'propertyAddress', 'submitterEmail', 'description', 'propertyType',
        'termsAccepted', 'submitButton', 'updateTitle', 'updateAddress', 'updateButton']) {
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
