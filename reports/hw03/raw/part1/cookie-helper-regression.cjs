// Deterministic review regression for the actual collector's login helper.
// The companion timestamp-boundary proof demonstrates Starlette's real re-signing.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../../..');
const source = fs.readFileSync(path.join(root, 'tests/browser_hw03_auth.cjs'), 'utf8');
const helper = source.slice(source.indexOf('async function login(page)'), source.indexOf('\nasync function anonymousHome'));
assert(helper.includes('async function login(page)'));
const BASE_URL = 'https://test.invalid';
const response = {
  status: () => 303,
  allHeaders: async () => ({ location: '/dashboard' }),
  headersArray: async () => [{ name: 'Set-Cookie', value: 'session=issued-at-1000; HttpOnly; Secure; SameSite=lax' }],
};
const cookie = { name: 'session', value: 'renewed-at-1001', secure: true, httpOnly: true, sameSite: 'Lax' };
const context = vm.createContext({ assert, BASE_URL, knownTokens: new Set(), responseSummary: async () => ({
  headers: [{ name: 'set-cookie', value: 'session=[REDACTED]; HttpOnly; Secure; SameSite=lax' }],
}) });
vm.runInContext(`${helper}\nthis.login = login;`, context);
function page(sent) {
  const element = { fill: async () => {}, click: async () => {}, waitFor: async () => {}, innerText: async () => 'admin' };
  return {
    goto: async () => {}, locator: () => element, getByRole: () => element,
    waitForResponse: () => Promise.resolve(response),
    waitForRequest: () => Promise.resolve({ allHeaders: async () => ({ cookie: `session=${sent}` }) }),
    waitForURL: async () => {}, context: () => ({ cookies: async () => [cookie] }),
  };
}
(async () => {
  const result = await context.login(page('issued-at-1000'));
  assert.equal(result.dashboard_request_sent_session_cookie, true);
  assert.equal(result.cookie.value, 'renewed-at-1001');
  await assert.rejects(() => context.login(page('unrelated-cookie')), /login-issued cookie/);
  console.log('PASS: actual helper accepts the login-issued request cookie when the later jar cookie differs.');
  console.log('PASS: actual helper retains the renewed jar cookie for replay and rejects an unrelated sent cookie.');
})().catch((error) => { console.error(error); process.exitCode = 1; });
