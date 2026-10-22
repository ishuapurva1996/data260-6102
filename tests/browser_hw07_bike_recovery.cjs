// Controlled HTTP responses test browser recovery; this is not a model measurement.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');
const BASE = 'https://127.0.0.1:8702';
const id = 'b'.repeat(32);
const output = process.env.HW7_BROWSER_OUTPUT;
async function main() {
  assert(output, 'Set an external capture directory');
  await fs.mkdir(output, { recursive: false });
  const browser = await chromium.launch({ headless: true });
  const result = { student:'Pragya Apurva', kind:'real Chromium with controlled bike HTTP responses; real login; no model calls', started_at:new Date().toISOString(), checks:[] };
  try {
    const context = await browser.newContext({ ignoreHTTPSErrors:true, viewport:{width:1440,height:1000} });
    const page = await context.newPage();
    let posts=0, polls=0, terminal=false;
    await page.route('**/api/bikeshare/runs', async route => {
      assert.equal(route.request().method(), 'POST');posts++;
      await route.fulfill({status:202,json:{run_id:id,status:'queued'}});
    });
    await page.route('**/api/bikeshare/runs/*', async route => {
      polls++;
      if (polls===1) return route.fulfill({status:503,json:{detail:'controlled transient status failure'}});
      await route.fulfill({status:200,json:{run_id:id,status:terminal?'completed':'running',error:null,events:[],result:terminal?{run_id:id,decision:null,verification:{passed:false,failures:['controlled_browser_fixture']},metrics:{stop_reason:'human_review',steps:0,model_requests:0,tool_calls:0,total_tokens:0,latency_ms:0},citations:[],weekly:[],assumptions:[]}:null}});
    });
    async function login(role) {
      await page.goto(BASE+'/login');
      await page.getByLabel('Username',{exact:true}).fill(process.env[`HW7_${role.toUpperCase()}_USERNAME`]);
      await page.getByLabel('Password',{exact:true}).fill(process.env[`HW7_${role.toUpperCase()}_PASSWORD`]);
      await page.getByRole('button',{name:'Log in',exact:true}).click();
      await page.getByRole('link',{name:'Bike-share',exact:true}).click();
      await page.getByRole('heading',{name:'Bike-share cost comparison',exact:true}).waitFor();
    }
    await login('reader');
    await page.locator('input[type=file]').setInputFiles(path.resolve(__dirname,'../reports/hw07/cases/bikeshare/frequent.csv'));
    await page.getByRole('button',{name:'Run',exact:true}).click();
    await page.getByText('Status refresh failed. Retrying the existing run; no new comparison was submitted.',{exact:true}).waitFor();
    assert(await page.getByRole('button',{name:'Running…',exact:true}).isDisabled());
    const recovered = page.waitForResponse(r=>r.url().endsWith('/api/bikeshare/runs/'+id) && r.status()===200);
    await recovered;
    result.checks.push('transient GET failure retries same run with Run disabled');
    await page.getByRole('link',{name:'Home',exact:true}).click();
    terminal=true;
    await page.getByRole('link',{name:'Bike-share',exact:true}).click();
    await page.getByText('Run completed',{exact:true}).waitFor();
    assert(await page.getByText('Run '+id,{exact:true}).isVisible());
    assert.equal(posts,1);
    result.checks.push('navigation returns to same terminal run without another POST');
    await page.screenshot({path:path.join(output,'controlled-recovered.png'),fullPage:true});
    await page.getByRole('button',{name:'Log out',exact:true}).click();
    await page.getByRole('heading',{name:'Log in',exact:true}).waitFor();
    await login('writer');
    assert.equal(await page.getByText('Run '+id,{exact:true}).count(),0);
    assert.equal(await page.locator('.bike-results').count(),0);
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    result.checks.push('account switch clears in-memory run handle and result; no browser storage');
    result.posts=posts;result.polls=polls;result.passed=true;
    await context.close();
  } finally {
    result.finished_at=new Date().toISOString();
    await fs.writeFile(path.join(output,'browser.json'),JSON.stringify(result,null,2)+'\n');
    await browser.close();
  }
  console.log('Pragya Apurva | PASS | controlled browser recovery | '+result.checks.join('; '));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
