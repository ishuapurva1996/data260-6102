#!/usr/bin/env node
// Run directly: node tests/browser_hw03_auth.cjs. Owns only servers it spawns.
// Requires the local .venv-web, Playwright 1.62.1, Chromium, and a SAN certificate.
const assert = require('node:assert/strict');
const { spawn, execFileSync } = require('node:child_process');
const { createHash, randomBytes } = require('node:crypto');
const fs = require('node:fs/promises');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const PYTHON = process.env.PYTHON || path.join(ROOT, '.venv-web', 'bin', 'python');
const HOST = process.env.HW3_HOST || '::1';
const PORT = Number(process.env.HW3_PORT || 8702);
const CERT = path.resolve(ROOT, process.env.HW3_CERT || 'tmp/https/cert.pem');
const KEY = path.resolve(ROOT, process.env.HW3_KEY || 'tmp/https/key.pem');
const BASE_URL = `https://${HOST.includes(':') ? `[${HOST}]` : HOST}:${PORT}`;
const RAW = path.join(ROOT, 'reports/hw03/raw/part1');
const SHOTS = path.join(ROOT, 'reports/hw03/screenshots/part1');
const SOURCE_ROOTS = [
  'code/web_application', 'requirements.txt', 'package.json',
  'tests/browser_hw03_auth.cjs', 'tests/browser_part2.cjs', 'tests/test_hw03_auth.py',
  'tests/test_api.py', 'scripts/run_hw03_web.py', 'scripts/verify_hw03_part1.py',
];
const knownTokens = new Set();
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const relative = (filename) => path.relative(ROOT, filename).split(path.sep).join('/');
const now = () => new Date().toISOString();
const evidence = {
  schema_version: 1,
  started_at: now(),
  status: 'running',
  command: 'node tests/browser_hw03_auth.cjs',
  cwd: ROOT,
  configuration: {
    base_url: BASE_URL, host: HOST, port: PORT,
    SID4: '6102', PORT_BASE: 8702, PREFIX: 's6102', SEED: 6102,
    VERIFY_SEED: 266102, DOMAIN_ID: 6, domain: 'Rental Housing Listings',
    normal_idle_timeout_seconds: 300, demonstration_idle_timeout_seconds: 2,
    certificate: relative(CERT), private_key: relative(KEY),
    certificate_exception: 'All automated browser contexts set ignoreHTTPSErrors: true for the local self-signed certificate; the OS trust store is unchanged.',
    cookie_value_handling: 'Live values remain in process memory only. The entire cookie value is redacted in saved response headers.',
  },
  checks: [], screenshots: [], server_phases: [],
};

function redact(text) {
  let safe = String(text);
  for (const token of knownTokens) safe = safe.split(token).join('[REDACTED]');
  return safe.replace(/(session=)[^;\s]+/gi, '$1[REDACTED]');
}

function readCommand(command, args) {
  return execFileSync(command, args, { cwd: ROOT, encoding: 'utf8' }).trim();
}

async function sourceHashes() {
  const files = [];
  async function walk(filename) {
    const stat = await fs.stat(filename);
    if (stat.isDirectory()) {
      for (const entry of (await fs.readdir(filename)).sort()) {
        if (entry !== '__pycache__' && entry !== '.pytest_cache') await walk(path.join(filename, entry));
      }
    } else if (stat.isFile() && !filename.endsWith('.pyc')) files.push(filename);
  }
  for (const name of SOURCE_ROOTS) await walk(path.join(ROOT, name));
  const hashes = {};
  for (const filename of files.sort()) {
    hashes[relative(filename)] = createHash('sha256').update(await fs.readFile(filename)).digest('hex');
  }
  return hashes;
}

async function check(name, run, page) {
  const result = { name, started_at: now(), status: 'running' };
  evidence.checks.push(result);
  try {
    result.details = await run();
    result.status = 'pass';
    console.log(`PASS ${name}`);
    return result.details;
  } catch (error) {
    result.status = 'fail';
    result.error = redact(error.stack || error);
    throw error;
  } finally {
    result.finished_at = now();
    if (page && !page.isClosed()) {
      result.actual_url = page.url();
      result.viewport = page.viewportSize();
    }
  }
}

async function assertPortAvailable() {
  const probe = net.createServer();
  await new Promise((resolve, reject) => {
    probe.once('error', (error) => reject(new Error(
      `Refusing to contact or stop any existing server: cannot bind ${HOST}:${PORT} (${error.code}).`,
    )));
    probe.listen({ host: HOST, port: PORT, ipv6Only: HOST.includes(':') }, resolve);
  });
  await new Promise((resolve, reject) => probe.close((error) => error ? reject(error) : resolve()));
  return { host: HOST, port: PORT, result: 'Bind succeeded, then probe socket closed; no HTTP request sent.' };
}

async function startServer(idleTimeout) {
  await check(`Port is available before ${idleTimeout}s server phase`, assertPortAvailable);
  const args = [
    '-m', 'uvicorn', 'main:app', '--app-dir', path.join(ROOT, 'code/web_application'),
    '--host', HOST, '--port', String(PORT), '--workers', '1', '--ssl-certfile', CERT, '--ssl-keyfile', KEY,
  ];
  const phase = {
    started_at: now(), idle_timeout_seconds: idleTimeout,
    executable: PYTHON, arguments: args,
    environment_overrides: { IDLE_TIMEOUT_SECONDS: String(idleTimeout), SECRET_KEY: '[RANDOM PER-PROCESS VALUE, NOT SAVED]' },
  };
  evidence.server_phases.push(phase);
  const secret = randomBytes(32).toString('hex');
  knownTokens.add(secret);
  const child = spawn(PYTHON, args, {
    cwd: ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: '1', IDLE_TIMEOUT_SECONDS: String(idleTimeout), SECRET_KEY: secret },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  let launchError;
  phase.pid = child.pid;
  child.on('error', (error) => { launchError = error; });
  for (const stream of [child.stdout, child.stderr]) {
    stream.on('data', (chunk) => { output = (output + chunk.toString()).slice(-40000); });
  }
  async function stop() {
    if (child.exitCode === null && child.signalCode === null && !launchError) {
      child.kill('SIGTERM');
      for (let attempt = 0; attempt < 50 && child.exitCode === null && child.signalCode === null; attempt += 1) await delay(100);
      if (child.exitCode === null && child.signalCode === null) {
        child.kill('SIGKILL');
        for (let attempt = 0; attempt < 20 && child.exitCode === null && child.signalCode === null; attempt += 1) await delay(100);
      }
    }
    phase.finished_at = now();
    phase.exit_code = child.exitCode;
    phase.signal = child.signalCode;
    phase.log_file = relative(path.join(RAW, `https-server-${idleTimeout}s.log`));
    await fs.writeFile(path.join(ROOT, phase.log_file), redact(output));
  }
  try {
    // Uvicorn emits this marker after binding. Do not probe another process if
    // there is a bind race or our child fails to launch.
    for (let attempt = 0; attempt < 150; attempt += 1) {
      if (launchError) throw launchError;
      if (child.exitCode !== null || child.signalCode !== null) throw new Error(`Owned HTTPS server exited before readiness:\n${redact(output)}`);
      if (/Uvicorn running on https:\/\//.test(output)) {
        phase.ready_at = now();
        return { stop };
      }
      await delay(100);
    }
    throw new Error(`Owned HTTPS server never reached listening state:\n${redact(output)}`);
  } catch (error) {
    await stop();
    throw error;
  }
}

async function snapshot(page, name) {
  await page.evaluate(() => document.fonts.ready);
  const dimensions = await page.evaluate(() => ({
    viewport_width: window.innerWidth,
    document_width: document.documentElement.scrollWidth,
    body_width: document.body.scrollWidth,
  }));
  assert(dimensions.document_width <= dimensions.viewport_width, `Document overflows: ${JSON.stringify(dimensions)}`);
  assert(dimensions.body_width <= dimensions.viewport_width, `Body overflows: ${JSON.stringify(dimensions)}`);
  const filename = path.join(SHOTS, `${name}.png`);
  await page.screenshot({ path: filename, fullPage: true, animations: 'disabled' });
  const capture = { file: relative(filename), captured_at: now(), actual_url: page.url(), viewport: page.viewportSize(), dimensions };
  evidence.screenshots.push(capture);
  return capture;
}

async function responseSummary(response) {
  const headers = [];
  for (const header of await response.headersArray()) {
    if (['date', 'server', 'content-type', 'location', 'cache-control', 'set-cookie'].includes(header.name.toLowerCase())) {
      let value = header.value;
      if (header.name.toLowerCase() === 'set-cookie') value = value.replace(/^([^=]+=)[^;]*/, '$1[REDACTED]');
      headers.push({ name: header.name, value: redact(value) });
    }
  }
  return { captured_at: now(), method: response.request().method(), url: response.url(), status: response.status(), headers };
}

async function redirectSummary(finalResponse) {
  const previous = finalResponse.request().redirectedFrom();
  assert(previous, 'Expected an actual server redirect before the final page');
  return responseSummary(await previous.response());
}

async function login(page) {
  await page.goto(`${BASE_URL}/login`);
  await page.locator('#username').fill('admin');
  await page.locator('#password').fill('password');
  const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/login' && response.request().method() === 'POST');
  const dashboardRequestPromise = page.waitForRequest((request) => new URL(request.url()).pathname === '/dashboard');
  await page.getByRole('button', { name: 'Login', exact: true }).click();
  const response = await responsePromise;
  assert.equal(response.status(), 303);
  assert.equal((await response.allHeaders()).location, '/dashboard');
  await page.waitForURL(`${BASE_URL}/dashboard`);
  await page.getByRole('heading', { name: 'Dashboard', exact: true }).waitFor();
  assert.match(await page.locator('main').innerText(), /admin/);
  const cookie = (await page.context().cookies(BASE_URL)).find((value) => value.name === 'session');
  assert(cookie, 'The login must create a browser session cookie');
  knownTokens.add(cookie.value);
  assert.equal(cookie.secure, true);
  assert.equal(cookie.httpOnly, true);
  assert.equal(cookie.sameSite, 'Lax');
  const issuedHeader = (await response.headersArray()).find((header) =>
    header.name.toLowerCase() === 'set-cookie' && header.value.startsWith('session='));
  assert(issuedHeader, 'The login response must issue the session cookie');
  const issuedCookie = issuedHeader.value.split(';', 1)[0];
  knownTokens.add(issuedCookie.slice('session='.length));
  const dashboardRequest = await dashboardRequestPromise;
  const sentCookie = (await dashboardRequest.allHeaders()).cookie || '';
  // The dashboard response may re-sign the jar cookie with a later timestamp.
  assert(sentCookie.split(';').some((value) => value.trim() === issuedCookie),
    'The browser must send the login-issued cookie on the HTTPS dashboard request');
  const summary = await responseSummary(response);
  const sessionHeader = summary.headers.find((header) => header.name.toLowerCase() === 'set-cookie' && header.value.startsWith('session='));
  assert(sessionHeader, 'The real login response must contain Set-Cookie');
  for (const attribute of [/;\s*httponly(?:;|$)/i, /;\s*secure(?:;|$)/i, /;\s*samesite=lax(?:;|$)/i]) {
    assert(attribute.test(sessionHeader.value), `Missing cookie attribute ${attribute}`);
  }
  return { cookie, summary, dashboard_request_sent_session_cookie: true };
}

async function anonymousHome(page) {
  assert.equal(new URL(page.url()).pathname, '/');
  assert.equal(await page.locator('nav').getByRole('link', { name: 'Login', exact: true }).isVisible(), true);
  assert.equal(await page.locator('nav').getByRole('link', { name: 'Logout', exact: true }).count(), 0);
  assert.equal(await page.locator('#rentalForm').isVisible(), true);
  await page.waitForFunction(() => document.querySelectorAll('#rentalList li[data-id]').length === 2);
}

async function replayDenied(browser, copiedCookie, name, viewport) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport });
  const page = await context.newPage();
  try {
    await context.addCookies([copiedCookie]);
    const requestPromise = page.waitForRequest((request) => new URL(request.url()).pathname === '/dashboard');
    const final = await page.goto(`${BASE_URL}/dashboard`);
    const actualRequest = await requestPromise;
    assert(((await actualRequest.allHeaders()).cookie || '').includes(`session=${copiedCookie.value}`), 'Fresh replay context must actually send the copied cookie');
    assert.equal(new URL(page.url()).pathname, '/login');
    assert.equal(final.status(), 200);
    const redirect = await redirectSummary(final);
    assert.equal(redirect.status, 303);
    assert.equal(redirect.headers.find((header) => header.name.toLowerCase() === 'location').value, '/login');
    await snapshot(page, name);
    return { fresh_browser_context: true, copied_cookie_actually_sent: true, final_url: page.url(), dashboard_response: redirect };
  } finally {
    await context.close();
  }
}

async function routeFlow(browser, label, viewport) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(redact(error.message)));
  page.setDefaultTimeout(12000);
  try {
    await check(`${label}: anonymous home and preserved rental controls`, async () => {
      assert.equal((await page.goto(BASE_URL)).status(), 200);
      await anonymousHome(page);
      return snapshot(page, `${label}-home`);
    }, page);
    await check(`${label}: login form`, async () => {
      await page.locator('nav').getByRole('link', { name: 'Login', exact: true }).click();
      await page.waitForURL(`${BASE_URL}/login`);
      assert.equal(await page.locator('#password').getAttribute('type'), 'password');
      return snapshot(page, `${label}-login`);
    }, page);
    await check(`${label}: anonymous dashboard is denied`, async () => {
      const response = await page.goto(`${BASE_URL}/dashboard`);
      assert.equal(new URL(page.url()).pathname, '/login');
      const redirect = await redirectSummary(response);
      assert.equal(redirect.status, 303);
      return redirect;
    }, page);
    await check(`${label}: invalid login shows the Bootstrap alert`, async () => {
      await page.locator('#username').fill('admin');
      await page.locator('#password').fill('incorrect-demo-password');
      const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/login' && response.request().method() === 'POST');
      await page.getByRole('button', { name: 'Login', exact: true }).click();
      const response = await responsePromise;
      assert.equal(response.status(), 401);
      await page.locator('.alert-danger[role="alert"]').waitFor();
      assert((await page.locator('.alert-danger').innerText()).trim().length > 0);
      assert.equal((await context.cookies(BASE_URL)).some((cookie) => cookie.name === 'session'), false);
      return { response_status: response.status(), screenshot: await snapshot(page, `${label}-invalid-login`) };
    }, page);
    let copiedCookie;
    await check(`${label}: valid HTTPS login and secure cookie attributes`, async () => {
      const result = await login(page);
      copiedCookie = { ...result.cookie };
      const filename = path.join(RAW, `${label}-login-response-headers.txt`);
      const text = [
        'Sanitized captured HTTP response headers (not a reconstructed server response)',
        `Captured: ${result.summary.captured_at}`, `${result.summary.method} ${result.summary.url}`,
        `HTTP status: ${result.summary.status}`,
        ...result.summary.headers.map((header) => `${header.name}: ${header.value}`),
        '', 'Redaction: the entire session cookie value is replaced; attributes are preserved.',
      ].join('\n');
      await fs.writeFile(filename, `${text}\n`);
      return {
        response: result.summary, header_file: relative(filename),
        dashboard_request_sent_session_cookie: result.dashboard_request_sent_session_cookie,
        screenshot: await snapshot(page, `${label}-dashboard`),
      };
    }, page);
    await check(`${label}: authenticated homepage navigation`, async () => {
      await page.goto(BASE_URL);
      assert.equal(await page.locator('nav').getByRole('link', { name: 'Dashboard', exact: true }).isVisible(), true);
      assert.equal(await page.locator('nav').getByRole('link', { name: 'Logout', exact: true }).isVisible(), true);
      assert.equal(await page.locator('nav').getByRole('link', { name: 'Login', exact: true }).count(), 0);
      return snapshot(page, `${label}-authenticated-home`);
    }, page);
    await check(`${label}: logout redirects to the anonymous homepage`, async () => {
      const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/logout');
      await page.locator('nav').getByRole('link', { name: 'Logout', exact: true }).click();
      await page.waitForURL(`${BASE_URL}/`);
      const response = await responsePromise;
      assert.equal(response.status(), 303);
      assert.equal((await response.allHeaders()).location, '/');
      await anonymousHome(page);
      assert.equal((await context.cookies(BASE_URL)).some((cookie) => cookie.name === 'session'), false);
      return { redirect: await responseSummary(response), screenshot: await snapshot(page, `${label}-post-logout`) };
    }, page);
    await check(`${label}: copied cookie cannot regain access after logout`, () => replayDenied(browser, copiedCookie, `${label}-logout-replay-denied`, viewport));
    await check(`${label}: browser JavaScript has no uncaught errors`, async () => {
      assert.deepEqual(errors, []);
      return { uncaught_errors: errors };
    }, page);
  } finally {
    await context.close();
  }
}

async function expiryFlow(browser) {
  const viewport = { width: 1280, height: 900 };
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  try {
    let copiedCookie;
    await check('Live expiry: login under the explicit 2-second demonstration timeout', async () => {
      const result = await login(page);
      copiedCookie = { ...result.cookie };
      assert.match(await page.locator('main').innerText(), /2(?:\.0)? seconds/);
      return { timeout_seconds: 2, screenshot: await snapshot(page, 'idle-before-expiry') };
    }, page);
    const waitStarted = Date.now();
    await delay(2300);
    evidence.live_expiry_wait = { started_at: new Date(waitStarted).toISOString(), elapsed_ms: Date.now() - waitStarted, requests_during_wait: 0 };
    // Replay FIRST, before the original context performs cleanup. This proves
    // elapsed idle time alone makes the copied, signed cookie insufficient.
    await check('Live expiry: copied cookie is denied in a fresh context after idle time', () => replayDenied(browser, copiedCookie, 'idle-replay-denied', viewport));
    await check('Live expiry: original browser session is denied on revisit', async () => {
      const response = await page.goto(`${BASE_URL}/dashboard`);
      assert.equal(new URL(page.url()).pathname, '/login');
      const redirect = await redirectSummary(response);
      assert.equal(redirect.status, 303);
      return { redirect, screenshot: await snapshot(page, 'idle-expired-login') };
    }, page);
  } finally {
    await context.close();
  }
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
}

async function evidencePanel(browser, title, description, content, filename) {
  const html = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escapeHTML(title)}</title>
  <style>body{font:17px/1.55 system-ui,sans-serif;margin:0;padding:42px;color:#172633;background:#f5f8fa}main{max-width:1120px;margin:auto}h1{font-size:29px;margin:0 0 12px}p{color:#435563}pre{font:16px/1.6 ui-monospace,monospace;background:white;border:1px solid #ccd6df;border-radius:8px;padding:25px;white-space:pre-wrap;overflow-wrap:anywhere}footer{color:#435563;font-size:14px}</style>
  <main><h1>${escapeHTML(title)}</h1><p>${escapeHTML(description)}</p><pre>${escapeHTML(content)}</pre><footer>HW3 Part 1 · Generated evidence viewer · ${escapeHTML(now())}</footer></main></html>`;
  const htmlFile = path.join(RAW, `${filename}.html`);
  await fs.writeFile(htmlFile, html);
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  try {
    await page.goto(pathToFileURL(htmlFile).href);
    return { viewer_file: relative(htmlFile), screenshot: await snapshot(page, filename) };
  } finally {
    await context.close();
  }
}

async function main() {
  let browser;
  let server;
  await fs.mkdir(RAW, { recursive: true });
  await fs.mkdir(SHOTS, { recursive: true });
  try {
    await check('Collect runtime and tested-source provenance', async () => {
      assert(Number.isInteger(PORT) && PORT > 0 && PORT < 65536, 'HW3_PORT must be a valid TCP port');
      await fs.access(CERT);
      await fs.access(KEY);
      evidence.tested_head = readCommand('git', ['rev-parse', 'HEAD']);
      evidence.source_sha256 = await sourceHashes();
      evidence.source_worktree_status = readCommand('git', ['status', '--short', '--', ...SOURCE_ROOTS]);
      evidence.runtime = {
        node: process.version, playwright: require('playwright/package.json').version,
        python_packages: JSON.parse(readCommand(PYTHON, ['-c', 'import sys,json,importlib.metadata as m; print(json.dumps({"python":sys.version,"packages":{n:m.version(n) for n in ["fastapi","starlette","uvicorn","jinja2","python-multipart","itsdangerous","httpx"]}}))'])),
        system: { platform: os.platform(), release: os.release(), architecture: os.arch(), cpu: os.cpus()[0]?.model, logical_cpus: os.cpus().length, memory_bytes: os.totalmem() },
      };
      assert.equal(evidence.runtime.playwright, '1.62.1');
      return { tested_head: evidence.tested_head, hashed_source_files: Object.keys(evidence.source_sha256).length };
    });
    server = await startServer(300);
    browser = await chromium.launch({ headless: true });
    evidence.runtime.chromium = browser.version();
    await routeFlow(browser, 'desktop', { width: 1280, height: 900 });
    await routeFlow(browser, 'mobile', { width: 375, height: 812 });
    await server.stop();
    server = undefined;
    server = await startServer(2);
    await expiryFlow(browser);
    await server.stop();
    server = undefined;
    evidence.configuration.timeout_restoration = 'The 2-second timeout was set only in the second owned child process environment. Both child servers were stopped; the application default remains 300 seconds.';
    await check('Capture sanitized real HTTP header evidence viewer', async () => evidencePanel(
      browser, 'Login cookie: sanitized captured HTTP headers',
      'These headers were captured from the real HTTPS login response. Only the entire cookie value is redacted. This is an evidence viewer, not a browser developer-tools screenshot.',
      await fs.readFile(path.join(RAW, 'desktop-login-response-headers.txt'), 'utf8'), 'cookie-header',
    ));
    await check('Capture actual templates directory listing evidence viewer', async () => {
      const directory = path.join(ROOT, 'code/web_application/templates');
      const listing = [];
      for (const name of (await fs.readdir(directory)).sort()) {
        const stat = await fs.stat(path.join(directory, name));
        listing.push({ name, type: stat.isDirectory() ? 'directory' : 'file', bytes: stat.size });
      }
      const captured = { captured_at: now(), directory: relative(directory), method: 'Node fs.readdir + fs.stat', entries: listing };
      await fs.writeFile(path.join(RAW, 'templates-directory.json'), `${JSON.stringify(captured, null, 2)}\n`);
      return evidencePanel(browser, 'Templates directory: captured file listing',
        'Actual filenames and byte sizes read from the worktree filesystem. This is a generated listing viewer, not a terminal screenshot.',
        [`Directory: ${captured.directory}`, `Captured: ${captured.captured_at}`, `Method: ${captured.method}`, '', ...listing.map((entry) => `${entry.name.padEnd(24)} ${String(entry.bytes).padStart(7)} bytes  (${entry.type})`)].join('\n'),
        'templates-directory');
    });
    await check('Source revision and hashes remain unchanged throughout browser evidence collection', async () => {
      assert.equal(readCommand('git', ['rev-parse', 'HEAD']), evidence.tested_head);
      assert.deepEqual(await sourceHashes(), evidence.source_sha256);
      return { unchanged: true };
    });
    evidence.status = 'pass';
  } catch (error) {
    evidence.status = 'fail';
    evidence.error = redact(error.stack || error);
    console.error(evidence.error);
    process.exitCode = 1;
  } finally {
    for (const cleanup of [() => browser?.close(), () => server?.stop()]) {
      try {
        await cleanup();
      } catch (error) {
        evidence.status = 'fail';
        evidence.cleanup_error = redact(error.stack || error);
        process.exitCode = 1;
      }
    }
    evidence.finished_at = now();
    evidence.pass_count = evidence.checks.filter((item) => item.status === 'pass').length;
    evidence.fail_count = evidence.checks.filter((item) => item.status === 'fail').length;
    await fs.writeFile(path.join(RAW, 'browser-evidence.json'), `${JSON.stringify(evidence, null, 2)}\n`);
    console.log(`${evidence.status.toUpperCase()}: ${evidence.pass_count} checks passed; ${evidence.screenshots.length} screenshots saved.`);
  }
}

main().catch((error) => {
  console.error(redact(error.stack || error));
  process.exitCode = 1;
});
