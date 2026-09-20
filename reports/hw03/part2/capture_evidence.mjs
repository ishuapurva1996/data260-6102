// Capture real browser views of saved experiment outputs; no image compositing.
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import crypto from 'node:crypto';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.HW3_PLAYWRIGHT_MODULE || 'playwright');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const options={headless:true};
if(process.env.HW3_BROWSER_PATH) options.executablePath=process.env.HW3_BROWSER_PATH;
const browser=await chromium.launch(options);
const page=await browser.newPage({viewport:{width:1500,height:1100},deviceScaleFactor:1});
const capture={captured_at:new Date().toISOString(),browser_version:browser.version(),
  viewport:{width:1500,height:1100},device_scale_factor:1,images:[]};
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
try {
  for(const name of ['token','semantic','sentence_window','metrics','failure']) {
    const source=path.join(root,'reports/hw03/part2/evidence_view',name+'.html');
    const destination=path.join(root,'reports/hw03/screenshots/part2',name+'.png');
    await page.goto('file://'+source);
    await page.screenshot({path:destination,fullPage:true});
    const dimensions=await page.evaluate(()=>({width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight}));
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    capture.images.push({name,title:await page.title(),dimensions,overflow,
      source:path.relative(root,source),source_sha256:hash(source),
      screenshot:path.relative(root,destination),screenshot_sha256:hash(destination)});
  }
} finally { await browser.close(); }
fs.writeFileSync(path.join(root,'reports/hw03/part2/screenshot_capture.json'),JSON.stringify(capture,null,2)+'\n');
console.log(JSON.stringify(capture,null,2));
