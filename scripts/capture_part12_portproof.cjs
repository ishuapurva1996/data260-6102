// Read-only proof of the existing app on the assignment port. No server control.
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..');
async function main() {
  const browser = await chromium.launch({ headless: true });
  const record = { at: new Date().toISOString(), purpose: 'Read-only inspection of the already-running assignment-port app; separate from the deterministic isolated sequence.', requests: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1100, height: 1100 }, deviceScaleFactor: 1 });
    page.on('request', (r) => { record.requests.push({ method: r.method(), url: r.url() }); });
    const response = await page.goto('http://127.0.0.1:8702/', { waitUntil: 'networkidle' });
    record.home = { url: page.url(), status: response.status() };
    await page.waitForFunction(() => document.querySelector('#searchForm').getAttribute('aria-busy') === 'false');
    const api = await page.request.get('http://127.0.0.1:8702/api/rentals');
    record.api = { method: 'GET', url: api.url(), status: api.status(), body: await api.json() };
    await page.locator('.list-section').evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 18));
    record.metrics = await page.evaluate(() => ({ innerWidth, innerHeight, devicePixelRatio, scrollY, documentScrollWidth: document.documentElement.scrollWidth }));
    record.screenshot = 'reports/hw02/screenshots/part2/P2-00-port8702-readonly.png';
    const png = await page.screenshot({ path: path.join(ROOT, record.screenshot), fullPage: false });
    record.pngWidth = png.readUInt32BE(16); record.pngHeight = png.readUInt32BE(20);
    record.sha256 = createHash('sha256').update(png).digest('hex');
    record.caption = 'Supplemental read-only verification of the existing application at http://127.0.0.1:8702/. This current state is not the seed baseline of the isolated 18702 sequence. URL and successful GET responses are in the adjacent JSON provenance; browser chrome is not part of this image.';
    assert(record.requests.every((r) => r.method === 'GET'));
    record.outcome = 'PASS';
    await fs.writeFile(path.join(ROOT, 'reports/hw02/raw/part12/port8702-readonly.json'), JSON.stringify(record, null, 2) + '\n');
    await fs.appendFile(path.join(ROOT, 'reports/hw02/RUN_LOG_PART12.txt'), `\n${record.at} Supplemental read-only port8702 proof: home GET ${record.home.status}, API GET ${record.api.status}, current IDs ${record.api.body.map((r) => r.id).join(',')}; no form submissions or mutation requests.\n`);
    console.log(JSON.stringify(record, null, 2));
  } finally { await browser.close(); }
}
main().catch((e) => { console.error(e.stack); process.exitCode = 1; });
