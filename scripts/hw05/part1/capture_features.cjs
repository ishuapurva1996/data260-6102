#!/usr/bin/env node
// Genuine browser frames: source read from this checkout above a LIVE app iframe.
// Requires owned app8702, unused viewer8703, private cert/key/login, explicit outputs.
const fs = require('node:fs');
const path = require('node:path');
const https = require('node:https');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const ROOT = path.resolve(__dirname, '../../..');
const BASE = 'https://localhost:8702';
const OUT = process.env.HW5_FEATURE_DIR;
const RAW = process.env.HW5_FEATURE_MANIFEST;
const escape = (s) => s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const source = (file, start, count) => {
  const lines=fs.readFileSync(path.join(ROOT,file),'utf8').split('\n');
  const index=lines.findIndex((line)=>line.includes(start)); assert(index>=0,start);
  return `<h3>${escape(file)}:${index+1}</h3><pre>${escape(lines.slice(index,index+count).join('\n'))}</pre>`;
};
const SLICE='frontend/src/features/rentals/rentalsSlice.js';
const sections={
  Home:source(SLICE,'export const fetchRentals',2)+source(SLICE,'.addCase(fetchRentals.fulfilled',5),
  Create:source(SLICE,'function mutation(',6)+source('frontend/src/api/client.js','create: (body, signal)',1),
  Update:source(SLICE,'export const updateRental',2)+source('frontend/src/pages/UpdateRecord.jsx','const { pending, error, submit }',3),
  Delete:source(SLICE,'export const deleteRental',1)+source(SLICE,'if (thunk === deleteRental)',3),
};
const html=`<!doctype html><html><head><meta charset="utf-8"><title>HW5 Redux source and live UI</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f4f7;color:#17202a;font:16px system-ui}header{height:58px;display:flex;align-items:center;gap:18px;padding:12px 24px;background:#142c28;color:white}select{font:inherit;padding:4px}#source{height:248px;overflow:hidden;display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:10px 22px;background:#fff}section{min-width:0}h3{font:13px monospace;margin:4px 0 8px}pre{font:15px/1.45 monospace;white-space:pre-wrap;margin:0}iframe{display:block;width:100%;height:1014px;border:0}footer{font:12px system-ui;padding:4px 22px}
</style></head><body><header><strong>Pragya Apurva · HW5 Redux</strong><label>Feature <select id="feature">${Object.keys(sections).map(k=>`<option>${k}</option>`).join('')}</select></label><span>Repository source + live application at localhost:8702</span></header><div id="source"></div><iframe title="Live rental application" src="${BASE}/login"></iframe><script>const sections=${JSON.stringify(sections)};const view=()=>{document.querySelector('#source').innerHTML=sections[document.querySelector('#feature').value].split(/(?=<h3>)/).filter(Boolean).map(s=>'<section>'+s+'</section>').join('')};document.querySelector('#feature').onchange=view;view();</script></body></html>`;
async function main(){
  assert(OUT&&RAW,'Set HW5_FEATURE_DIR and HW5_FEATURE_MANIFEST');
  fs.mkdirSync(OUT,{recursive:true});
  const server=https.createServer({cert:fs.readFileSync(process.env.HW5_CA_CERT),key:fs.readFileSync(process.env.HW5_TLS_KEY)},(req,res)=>{res.writeHead(200,{'Content-Type':'text/html','Cache-Control':'no-store'});res.end(html)});
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(8703,'127.0.0.1',resolve)});
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1700,height:1320}});
  const page=await context.newPage();page.setDefaultTimeout(20000);
  const captures=[];let ownedId;
  try{
    await page.goto('https://localhost:8703');
    const app=page.frameLocator('iframe');
    await app.getByLabel('Email',{exact:true}).fill(process.env.HW4_SEED_EMAIL);
    await app.getByLabel('Password',{exact:true}).fill(process.env.HW4_SEED_PASSWORD);
    await app.getByRole('button',{name:'Log in',exact:true}).click();
    await app.locator('.result-count').waitFor();
    async function capture(feature){
      await page.locator('#feature').selectOption(feature);
      const filename=path.join(OUT,`${feature.toLowerCase()}.png`);
      await page.screenshot({path:filename,animations:'disabled'});
      captures.push({feature,file:path.relative(ROOT,filename),captured_at:new Date().toISOString(),live_url:page.frames().find(f=>f.url().startsWith(BASE)).url(),source_file:SLICE});
      console.log(`CAPTURED ${feature}: genuine browser source + live UI frame`);
    }
    await capture('Home');
    const managers=await (await context.request.get(BASE+'/api/property-managers?limit=1')).json();assert(managers.length);
    await app.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Add listing',exact:true}).click();
    const title='HW5 Sunlit Campus Apartment';
    await app.getByLabel('Listing title',{exact:true}).fill(title);
    await app.getByLabel('Property address',{exact:true}).fill('6102 Redux Lane, San Jose, CA');
    await app.getByLabel('Available units',{exact:true}).fill('2');
    await app.getByLabel('Property manager',{exact:true}).selectOption(String(managers[0].id));
    await app.getByLabel('Landlord Email',{exact:true}).fill('redux-evidence@example.com');
    await app.getByLabel('Description',{exact:true}).fill('A comfortable demonstration rental close to campus and public transit.');
    await app.getByLabel('I accept the terms',{exact:true}).check();
    const created=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/rentals');
    await app.getByRole('button',{name:'Add listing',exact:true}).click();
    const response=await created;assert.equal(response.status(),201);ownedId=(await response.json()).id;
    await app.getByText('Listing added.',{exact:true}).waitFor();
    await app.locator('[data-mutation-result]').filter({hasText:title}).waitFor();
    await app.locator('.result-count').waitFor();await capture('Create');
    // Use the real application's normal navigation and selected record route.
    await app.getByLabel('Search listings').fill(title);await app.getByRole('button',{name:'Search',exact:true}).click();
    const row=app.locator(`article[data-record-id="${ownedId}"]`);await row.waitFor();
    await row.getByRole('link',{name:'Update',exact:true}).click();
    await app.getByRole('heading',{name:'Update listing',exact:true}).waitFor();
    await app.getByLabel('Listing title',{exact:true}).fill(title+' updated');
    await app.getByLabel('Available units',{exact:true}).fill('3');
    await app.getByRole('button',{name:'Save changes',exact:true}).click();
    await app.getByText('Listing updated.',{exact:true}).waitFor();
    await app.locator('[data-mutation-result]').filter({hasText:title+' updated'}).waitFor();
    await app.locator('.result-count').waitFor();await capture('Update');
    await app.getByLabel('Search listings').fill(title);await app.getByRole('button',{name:'Search',exact:true}).click();
    await row.waitFor();await row.getByRole('button',{name:'Delete',exact:true}).click();
    await app.getByText(`Deleted listing #${ownedId}`,{exact:true}).waitFor();
    await app.getByRole('heading',{name:'No listings found',exact:true}).waitFor();
    assert.equal((await context.request.get(BASE+`/api/rentals/${ownedId}`)).status(),404);
    ownedId=null;await capture('Delete');
    fs.writeFileSync(RAW,JSON.stringify({revision:execFileSync('git',['rev-parse','HEAD'],{cwd:ROOT,encoding:'utf8'}).trim(),captured_at:new Date().toISOString(),source_dirty:Boolean(execFileSync('git',['status','--porcelain'],{cwd:ROOT,encoding:'utf8'}).trim()),source_sha256:Object.fromEntries([SLICE,'frontend/src/pages/CreateRecord.jsx','frontend/src/pages/UpdateRecord.jsx','frontend/src/pages/Home.jsx','frontend/src/components/forms.jsx','scripts/hw05/part1/capture_features.cjs'].map(f=>[f,createHash('sha256').update(fs.readFileSync(path.join(ROOT,f))).digest('hex')])),provenance:'Single browser screenshots of a source viewer reading repository files and an embedded live HTTPS application. No screenshot compositing, response interception, or reconstructed app UI.',captures},null,2)+'\n');
  }finally{
    if(ownedId)await context.request.delete(BASE+`/api/rentals/${ownedId}`);
    await context.request.post(BASE+'/api/auth/logout');
    await context.close();await browser.close();await new Promise(r=>server.close(r));
  }
}
main().catch(e=>{console.error(String(e.message).replaceAll(process.env.HW4_SEED_PASSWORD||'\0','[REDACTED]'));process.exitCode=1});
