// Render saved-output HTML panels; this does not run models or contact the app.
const fs = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { createHash } = require('node:crypto');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..');
const MANIFEST = path.join(ROOT, 'reports/hw02/screenshots/final-panels/manifest.json');
const sha256 = (value) => createHash('sha256').update(value).digest('hex');
async function main() {
  const manifest = JSON.parse(await fs.readFile(MANIFEST, 'utf8'));
  const browser = await chromium.launch({ headless: true });
  const browserVersion = browser.version();
  const results = [];
  try {
    for (const panel of manifest.panels) {
      const html = await fs.readFile(path.join(ROOT, panel.html_path));
      const page = await browser.newPage({ viewport: { width: 900, height: 800 }, deviceScaleFactor: 1 });
      const url = pathToFileURL(path.join(ROOT, panel.html_path)).href;
      await page.goto(url, { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready);
      const visibleText = await page.locator('main').innerText();
      if (/Browser-rendered|Recorded working tree|hw2-code\s*@|See screenshot\s*\d/i.test(visibleText)) {
        throw new Error(`Remove screenshot footer labels before capture: ${panel.id}`);
      }
      const metrics = await page.locator('main').evaluate((el) => {
        const rect = el.getBoundingClientRect();
        return { width: rect.width, height: rect.height, scrollWidth: el.scrollWidth, scrollHeight: el.scrollHeight, documentScrollWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth, viewportHeight: innerHeight, devicePixelRatio };
      });
      const png = await page.locator('main').screenshot({ path: path.join(ROOT, panel.suggested_png_path), animations: 'disabled' });
      const dimensions = { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
      panel.html_sha256 = sha256(html);
      panel.png_path = panel.suggested_png_path;
      panel.png_sha256 = sha256(png);
      panel.png_width_px = dimensions.width;
      panel.png_height_px = dimensions.height;
      panel.captured_at = new Date().toISOString();
      panel.capture = {
        method: 'Playwright Chromium main-element PNG screenshot of the supplied local HTML',
        provenance: 'Browser screenshots of saved output and result tables. Technical provenance is retained in the sidecar manifest, outside the image. No new model calls, pixel overlays or image reconstruction.',
        browser_version: browserVersion,
        playwright_version: require('playwright/package.json').version,
        page_url: url, metrics,
        within_target_height: dimensions.height <= panel.target_max_height_px,
        no_horizontal_overflow: metrics.documentScrollWidth === 900 && metrics.scrollWidth === 900,
      };
      results.push({ id: panel.id, ...dimensions, target: panel.target_max_height_px, withinTarget: panel.capture.within_target_height });
      await page.close();
    }
    manifest.capture_needed = false;
    manifest.capture_completed_at = new Date().toISOString();
    manifest.capture_provenance = 'Nine unaltered Chromium element screenshots of the supplied HTML saved-output panels. No app server access or model execution.';
    manifest.validation.rendered_height = results.every((r) => r.withinTarget) ? 'PASS: all nine images fit their individual height targets at 900px width.' : 'Some images exceed height targets; see per-panel capture metadata.';
    manifest.p3_validation.rendered_heights = results.filter((r) => r.id.startsWith('P3'));
    await fs.writeFile(MANIFEST, JSON.stringify(manifest, null, 2) + '\n');
    console.log(JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
}
main().catch((error) => { console.error(error.stack); process.exitCode = 1; });
