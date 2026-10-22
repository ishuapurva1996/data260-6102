// Genuine Chromium acceptance; credentials enter through the existing private environment.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '../..');
const BASE = process.env.HW7_BROWSER_BASE || 'https://127.0.0.1:8702';
const output = process.env.HW7_BROWSER_OUTPUT;
const scenario = process.env.HW7_BIKE_SCENARIO || 'ui';
const summary = { student: 'Pragya Apurva', evidence_kind: 'live Chromium + HTTPS + MySQL authentication; real framework/model when scenario is supplied', scenario, started_at: new Date().toISOString(), checks: [], requests: [], screenshots: [], errors: [] };
const matches = (method, pathname) => r => r.request().method() === method && new URL(r.url()).pathname === pathname;
async function main() {
  assert(output && !path.resolve(output).startsWith(ROOT + path.sep), 'Use a fresh external capture directory');
  assert(['ui', 'frequent', 'occasional'].includes(scenario));
  await fs.mkdir(output, { recursive: false });
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    page.on('pageerror', e => summary.errors.push(e.message));
    page.on('response', r => {
      const pathname = new URL(r.url()).pathname;
      if (pathname.startsWith('/api/') || pathname.startsWith('/auth/')) summary.requests.push({ method: r.request().method(), path: pathname, status: r.status(), bearer: /^Bearer /.test(r.request().headers().authorization || ''), at: new Date().toISOString() });
    });
    const role = scenario === 'ui' ? 'writer' : 'reader';
    await page.goto(BASE + '/login');
    await page.getByLabel('Username', { exact: true }).fill(process.env[`HW7_${role.toUpperCase()}_USERNAME`]);
    await page.getByLabel('Password', { exact: true }).fill(process.env[`HW7_${role.toUpperCase()}_PASSWORD`]);
    const login = page.waitForResponse(matches('POST', '/auth/login'));
    await page.getByRole('button', { name: 'Log in', exact: true }).click();
    const authenticated = await login;
    assert.equal(authenticated.status(), 200);
    const token = (await authenticated.json()).access_token;
    await page.getByRole('link', { name: 'Bike-share', exact: true }).click();
    await page.getByRole('heading', { name: 'Bike-share cost comparison', exact: true }).waitFor();
    assert.equal(await page.locator('input[type=file]').count(), 1);
    assert.equal(await page.locator('input[type=url]').count(), 1);
    assert.equal(await page.getByRole('button', { name: 'Run', exact: true }).count(), 1);
    summary.checks.push('real UI login, bearer authentication, one CSV field, one URL field, one Run button');
    async function capture(name, options = {}) {
      const file = name + '.png';
      await page.screenshot({ path: path.join(output, file), ...options });
      const bytes = await fs.readFile(path.join(output, file));
      summary.screenshots.push({ file, sha256: createHash('sha256').update(bytes).digest('hex'), captured_at: new Date().toISOString(), viewport: page.viewportSize(), full_page: Boolean(options.fullPage) });
    }
    async function noOverflow(width) {
      await page.setViewportSize({ width, height: 1000 });
      const sizes = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
      assert(sizes.document <= sizes.viewport, `horizontal overflow at ${width}px: ${JSON.stringify(sizes)}`);
      summary.checks.push(`no document overflow at ${width}px`);
    }
    if (scenario === 'ui') {
      for (const width of [1440, 740, 680, 390]) {
        await noOverflow(width);
        await capture('input-' + width, { fullPage: true });
      }
    } else {
      await page.locator('input[type=file]').setInputFiles(path.join(ROOT, 'reports/hw07/cases/bikeshare', scenario + '.csv'));
      await page.getByLabel('Official pricing URL', { exact: true }).fill('https://capitalbikeshare.com/pricing');
      const submitted = page.waitForResponse(matches('POST', '/api/bikeshare/runs'));
      await page.getByRole('button', { name: 'Run', exact: true }).click();
      const response = await submitted;
      assert.equal(response.status(), 202);
      const runId = (await response.json()).run_id;
      summary.run_id = runId;
      await page.getByText(/Run completed|Run stopped/, { exact: true }).waitFor({ timeout: 720000 });
      const terminal = await context.request.get(BASE + '/api/bikeshare/runs/' + runId, { headers: { Authorization: 'Bearer ' + token } });
      assert.equal(terminal.status(), 200);
      const data = await terminal.json();
      await fs.writeFile(path.join(output, 'response.json'), JSON.stringify(data, null, 2) + '\n');
      summary.result = data.result;
      // Capture failures too; assertions below never replace a failed model result.
      await noOverflow(1440);
      await page.evaluate(() => scrollTo(0, 0));
      await capture('overview');
      await capture('full', { fullPage: true });
      for (const [name, selector] of [['weekly','#bike-weekly-title'], ['assumptions','#bike-break-even-title'], ['citations','#bike-citations-title']]) {
        assert.equal(await page.locator(selector).count(), 1, `required ${name} panel exists`);
        await page.locator(selector).scrollIntoViewIfNeeded();
        assert(await page.locator(selector).isVisible(), `required ${name} panel is visible`);
        await capture(name);
      }
      assert(await page.locator('.bike-table tbody tr').count() > 0, 'weekly rows exist');
      assert(await page.locator('.bike-citations li').count() >= 3, 'captured sources exist');
      assert(await page.locator('.bike-calls > li').count() > 0, 'actual tool observations exist');
      assert(await page.locator('.bike-metrics').isVisible(), 'metrics strip is visible');
      for (const width of [740, 390]) await noOverflow(width);
      assert(data.result, 'run produced a terminal result');
      assert.equal(data.result.source_dirty, false, 'acceptance source must be committed');
      assert.equal(data.result.verification.passed, true, JSON.stringify(data.result.verification));
      assert.equal(data.result.metrics.stop_reason, 'success');
      assert.equal(data.result.row_count, 500);
      assert.equal(data.result.decision, scenario === 'frequent' ? 'Buy Monthly Membership' : 'Pay Per Ride/Minute');
      assert.equal(summary.requests.filter(r => r.method === 'POST' && r.path === '/api/bikeshare/runs').length, 1);
      summary.checks.push('one genuine UI submission, real worker, verified expected decision, all result panels, responsive result layout');
    }
    assert.deepEqual(summary.errors, []);
    await context.close();
  } finally {
    summary.finished_at = new Date().toISOString();
    await fs.writeFile(path.join(output, 'browser.json'), JSON.stringify(summary, null, 2) + '\n');
    await browser.close();
  }
  console.log('Pragya Apurva | browser acceptance passed | ' + scenario + ' | ' + summary.checks.join('; '));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
