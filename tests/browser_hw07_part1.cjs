// Live browser acceptance. Credentials and captures stay in external runtime paths.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium, request } = require('playwright');
const BASE = process.env.HW7_BROWSER_BASE || 'https://127.0.0.1:8702';
const output = process.env.HW7_BROWSER_OUTPUT;
const result = { student: 'Pragya Apurva', evidence_kind: 'live Chromium, HTTPS and MySQL; no mocked responses',
  started_at: new Date().toISOString(), checks: [], requests: [] };
const match = (method, pathname) => r => r.request().method() === method && new URL(r.url()).pathname === pathname;
async function main() {
  assert(output, 'Set HW7_BROWSER_OUTPUT to an external directory');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const api = await request.newContext({ baseURL: BASE, ignoreHTTPSErrors: true });
  let ownedId = null;
  async function credentials(role) {
    return { username: process.env[`HW7_${role.toUpperCase()}_USERNAME`], password: process.env[`HW7_${role.toUpperCase()}_PASSWORD`] };
  }
  async function login(page, role) {
    await page.goto(BASE + '/login');
    const auth = await credentials(role);
    await page.getByLabel('Username', { exact: true }).fill(auth.username);
    await page.getByLabel('Password', { exact: true }).fill(auth.password);
    const loginResponse = page.waitForResponse(match('POST', '/auth/login'));
    const meResponse = page.waitForResponse(match('GET', '/auth/me'));
    await page.getByRole('button', { name: 'Log in', exact: true }).click();
    assert.equal((await loginResponse).status(), 200);
    assert.equal((await meResponse).status(), 200);
    await page.locator('.result-count').waitFor();
    assert((await page.locator('.session-line').innerText()).includes(role));
  }
  async function check(name, action) {
    await action();
    result.checks.push({ name, passed: true, at: new Date().toISOString() });
    console.log('Pragya Apurva | PASS | ' + name);
  }
  async function capture(page, name) {
    const sizes = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
    assert(sizes.document <= sizes.viewport, 'No horizontal overflow');
    await page.screenshot({ path: path.join(output, name + '.png'), fullPage: true });
  }
  try {
    for (const width of [1280, 390]) {
      const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width, height: 900 } });
      const page = await context.newPage();
      page.on('request', r => {
        const pathname = new URL(r.url()).pathname;
        if (pathname.startsWith('/api/') || pathname.startsWith('/auth/')) {
          result.requests.push({ method: r.method(), path: pathname,
            bearer: /^Bearer /.test(r.headers().authorization || ''),
            cookie: Boolean(r.headers().cookie), at: new Date().toISOString() });
        }
      });
      await check(`${width}px reader login, bearer identity and list`, async () => {
        await login(page, 'reader');
        assert.equal(await page.getByRole('link', { name: 'Add listing', exact: true }).count(), 0);
        await capture(page, `reader-${width}`);
      });
      await check(`${width}px forbidden create route explains permission`, async () => {
        await page.evaluate(() => { history.pushState({}, '', '/create'); dispatchEvent(new PopStateEvent('popstate')); });
        await page.getByRole('heading', { name: 'Permission required' }).waitFor();
        await capture(page, `reader-forbidden-${width}`);
      });
      await check(`${width}px reload clears memory token`, async () => {
        await page.reload();
        await page.getByRole('heading', { name: 'Login required' }).waitFor();
        assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
        assert.equal((await context.cookies()).length, 0);
      });
      await context.close();
    }
    const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 1000 } });
    const page = await context.newPage();
    await check('writer creates an owned listing through the existing form', async () => {
      await login(page, 'writer');
      assert.equal(await page.getByRole('button', { name: 'Delete', exact: true }).count(), 0);
      await page.getByRole('link', { name: 'Add listing', exact: true }).first().click();
      await page.getByRole('heading', { name: 'Add a rental listing' }).waitFor();
      const marker = 'HW7 browser ' + randomUUID();
      await page.getByLabel('Listing title', { exact: true }).fill(marker);
      await page.getByLabel('Property address', { exact: true }).fill('10 Browser Test Lane, San Jose');
      await page.getByLabel('Landlord Email', { exact: true }).fill('hw7-browser@example.com');
      await page.getByLabel('Description', { exact: true }).fill(marker + ' owned browser fixture.');
      await page.locator('[name=managerId] option:not([value=""])').first().waitFor({ state: 'attached' });
      const manager = await page.locator('[name=managerId] option:not([value=""])').first().getAttribute('value');
      await page.getByLabel('Property manager', { exact: true }).selectOption(manager);
      await page.getByLabel('I accept the terms', { exact: true }).check();
      const created = page.waitForResponse(match('POST', '/api/rentals'));
      await page.getByRole('button', { name: 'Add listing', exact: true }).click();
      const response = await created;
      assert.equal(response.status(), 201);
      ownedId = (await response.json()).id;
      await page.locator('[data-mutation-result]').waitFor();
      await capture(page, 'writer-created');
    });
    await check('real 401 clears identity and protected data (controlled invalid bearer)', async () => {
      await page.evaluate(() => { history.pushState({}, '', '/'); dispatchEvent(new PopStateEvent('popstate')); });
      await page.locator('.result-count').waitFor();
      await page.route('**/api/rentals**', async route => {
        await route.continue({ headers: { ...route.request().headers(), Authorization: 'Bearer invalid.browser.probe' } });
      }, { times: 1 });
      const denied = page.waitForResponse(match('GET', '/api/rentals'));
      await page.getByRole('button', { name: 'Search', exact: true }).click();
      assert.equal((await denied).status(), 401);
      await page.getByRole('heading', { name: 'Log in', exact: true }).waitFor();
      assert.equal(await page.locator('article').count(), 0);
      await capture(page, 'expired-session');
      await login(page, 'writer');
    });
    await check('logout clears identity and protected data', async () => {
      await page.getByRole('button', { name: 'Log out', exact: true }).click();
      await page.getByRole('heading', { name: 'Log in', exact: true }).waitFor();
      await page.evaluate(() => { history.pushState({}, '', '/'); dispatchEvent(new PopStateEvent('popstate')); });
      await page.getByRole('heading', { name: 'Login required' }).waitFor();
      assert.equal(await page.locator('article').count(), 0);
    });
    await check('moderator deletes only the owned browser listing', async () => {
      await login(page, 'moderator');
      await page.evaluate(id => { history.pushState({}, '', '/delete?id=' + id); dispatchEvent(new PopStateEvent('popstate')); }, ownedId);
      await page.getByRole('heading', { name: 'Delete listing', exact: true }).waitFor();
      const deleted = page.waitForResponse(match('DELETE', '/api/rentals/' + ownedId));
      await page.getByRole('button', { name: 'Delete listing', exact: true }).click();
      assert.equal((await deleted).status(), 204);
      ownedId = null;
      await page.locator('[data-mutation-result]').waitFor();
      await capture(page, 'moderator-deleted');
    });
    await context.close();
    assert(result.requests.filter(r => r.path.startsWith('/api/')).every(r => r.bearer && !r.cookie));
    result.passed = true;
  } finally {
    if (ownedId) {
      const response = await api.post('/auth/login', { data: await credentials('moderator') });
      const token = (await response.json()).access_token;
      assert.equal((await api.delete('/api/rentals/' + ownedId, { headers: { Authorization: 'Bearer ' + token } })).status(), 204);
    }
    result.finished_at = new Date().toISOString();
    await fs.writeFile(path.join(output, 'browser.json'), JSON.stringify(result, null, 2) + '\n');
    await api.dispose();
    await browser.close();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
