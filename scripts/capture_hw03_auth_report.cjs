// Supplementary report figures; the authoritative 27-check suite remains separate.
const assert = require('node:assert/strict');
const {spawn, execFileSync} = require('node:child_process');
const {createHash, randomBytes} = require('node:crypto');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');
const ROOT = path.resolve(__dirname, '..');
const RAW = path.join(ROOT, 'reports/hw03/raw/integration');
const SHOTS = path.join(ROOT, 'reports/hw03/screenshots/integration');
const BASE = 'https://[::1]:8702';
const rel = filename => path.relative(ROOT, filename);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const sha = filename => digest(fs.readFileSync(filename));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

(async () => {
  fs.mkdirSync(SHOTS, {recursive: true});
  fs.mkdirSync(path.join(RAW, 'evidence_view'), {recursive: true});
  const sourcePath = path.join(ROOT, 'reports/hw03/raw/part1/browser-evidence.json');
  const source = JSON.parse(fs.readFileSync(sourcePath, 'utf8'));
  assert.equal(source.status, 'pass');
  for (const [name, expected] of Object.entries(source.source_sha256)) {
    assert.equal(sha(path.join(ROOT, name)), expected, `Changed tested source: ${name}`);
  }
  const receipt = {started_at: new Date().toISOString(), status: 'running',
    purpose: 'Actual mobile viewport captures plus browser views of saved redacted headers and directory evidence.',
    tested_runtime_commit: source.tested_head,
    capture_checkout: execFileSync('git', ['rev-parse', 'HEAD'], {cwd: ROOT, encoding: 'utf8'}).trim(),
    source_sha256: {[rel(sourcePath)]: sha(sourcePath), [rel(__filename)]: sha(__filename)}, images: []};
  const probe = net.createServer();
  await new Promise((resolve, reject) => {
    probe.once('error', reject);
    probe.listen({host: '::1', port: 8702, ipv6Only: true}, resolve);
  });
  await new Promise(resolve => probe.close(resolve));
  const server = spawn(path.join(ROOT, '.venv-web/bin/python'), [
    '-m', 'uvicorn', 'main:app', '--app-dir', path.join(ROOT, 'code/web_application'),
    '--host', '::1', '--port', '8702', '--workers', '1',
    '--ssl-certfile', path.join(ROOT, 'tmp/https/cert.pem'),
    '--ssl-keyfile', path.join(ROOT, 'tmp/https/key.pem'),
  ], {cwd: ROOT, env: {...process.env, IDLE_TIMEOUT_SECONDS: '300', SECRET_KEY: randomBytes(32).toString('hex')}, stdio: 'ignore'});
  let launchError;
  server.on('error', error => { launchError = error; });
  let browser;
  try {
    browser = await chromium.launch({headless: true});
    receipt.browser_version = browser.version();
    const page = await browser.newPage({viewport: {width: 375, height: 812}, ignoreHTTPSErrors: true});
    for (let i = 0; i < 50; i++) {
      if (launchError) throw launchError;
      if (server.exitCode !== null) throw new Error('Own HTTPS server exited before readiness');
      try { await page.goto(BASE, {timeout: 1000}); break; }
      catch (error) { if (i === 49) throw error; await pause(100); }
    }
    async function capture(name, kind) {
      await page.evaluate(() => document.fonts.ready);
      const target = path.join(SHOTS, `${name}.png`);
      const bytes = await page.screenshot({path: target, fullPage: false});
      receipt.images.push({name, kind, captured_at: new Date().toISOString(), url: page.url(),
        viewport: page.viewportSize(), screenshot: rel(target), sha256: digest(bytes)});
    }
    assert.equal(await page.locator('a[href="/login"]').count() > 0, true);
    await capture('auth-home', 'actual application viewport');
    await page.goto(BASE + '/login');
    await page.locator('[name="username"]').fill('admin');
    await page.locator('[name="password"]').fill('password');
    await Promise.all([page.waitForURL('**/dashboard'), page.locator('button[type="submit"]').click()]);
    await page.goto(BASE);
    assert.equal(await page.locator('a[href="/dashboard"]').count() > 0, true);
    await capture('auth-authenticated-home', 'actual application viewport');
    await page.goto(BASE + '/logout');
    assert.equal(page.url(), BASE + '/');
    assert.equal(await page.locator('a[href="/login"]').count() > 0, true);
    await capture('auth-post-logout', 'actual application viewport after logout redirect');

    await page.setViewportSize({width: 1000, height: 650});
    async function viewer(name, title, filename, transform) {
      const absolute = path.join(ROOT, filename);
      receipt.source_sha256[filename] = sha(absolute);
      const body = transform(fs.readFileSync(absolute, 'utf8'));
      const htmlPath = path.join(RAW, 'evidence_view', name + '.html');
      fs.writeFileSync(htmlPath, `<!doctype html><meta charset="utf-8"><title>${title}</title><style>body{padding:24px;margin:0;font:20px/1.4 system-ui;color:#17354d}h1{font-size:28px}pre{font:20px/1.4 Menlo,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f8;padding:16px}p{font-size:16px}</style><h1>${title}</h1><pre>${escape(body)}</pre><p>Browser view of saved evidence, reflowed for readability. Values unchanged. Source: ${filename}</p>`);
      receipt.source_sha256[rel(htmlPath)] = sha(htmlPath);
      await page.goto(pathToFileURL(htmlPath).href);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight), true, 'Viewer must fit its screenshot');
      await capture(name, 'browser view of saved evidence');
    }
    await viewer('auth-cookie-header', 'Captured HTTPS login response', 'reports/hw03/raw/part1/desktop-login-response-headers.txt', text => {
      const cookies = [...text.matchAll(/session=([^;\s]+)/gi)];
      if (!cookies.length || cookies.some(match => match[1] !== '[REDACTED]')) {
        throw new Error('Refusing to render session headers without complete cookie-value redaction');
      }
      return text;
    });
    await page.setViewportSize({width: 1000, height: 500});
    await viewer('auth-templates-directory', 'Captured templates directory', 'reports/hw03/raw/part1/templates-directory.json', text => {
      const listing = JSON.parse(text);
      return `Directory: ${listing.directory}\nCaptured: ${listing.captured_at}\n\n` + listing.entries.map(item => `${item.name.padEnd(22)} ${String(item.bytes).padStart(5)} bytes (${item.type})`).join('\n');
    });
    receipt.status = 'pass';
  } finally {
    let cleanupError;
    try { if (browser) await browser.close(); }
    catch (error) { cleanupError = error; }
    try {
      if (server.exitCode === null && server.signalCode === null && !launchError) {
        server.kill('SIGTERM');
        for (let i = 0; i < 50 && server.exitCode === null && server.signalCode === null; i++) await pause(100);
        if (server.exitCode === null && server.signalCode === null) {
          server.kill('SIGKILL');
          for (let i = 0; i < 20 && server.exitCode === null && server.signalCode === null; i++) await pause(100);
          if (server.exitCode === null && server.signalCode === null) throw new Error('Own HTTPS server did not exit');
        }
      }
    } catch (error) { cleanupError ||= error; }
    if (cleanupError || receipt.status !== 'pass') receipt.status = 'fail';
    if (cleanupError) {
      receipt.cleanup_error = 'Browser or owned HTTPS server cleanup failed';
    }
    receipt.finished_at = new Date().toISOString();
    fs.writeFileSync(path.join(RAW, 'auth-report-capture.json'), JSON.stringify(receipt, null, 2) + '\n');
    if (cleanupError) throw cleanupError;
  }
  console.log(`Captured ${receipt.images.length} supplementary report figures: ${receipt.status}`);
})().catch(error => { console.error(error.message); process.exitCode = 1; });
