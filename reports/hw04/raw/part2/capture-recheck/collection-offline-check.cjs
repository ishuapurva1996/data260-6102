'use strict';
// Offline stub only: compiles/runs saved Postman scripts without Postman or HTTP.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const path = require('node:path');
const repo = '/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend';
const source = path.join(repo, 'reports/hw04/part2/postman_collection.json');
const output = path.join(repo, 'reports/hw04/raw/part2/capture-recheck');
const started = new Date().toISOString();
const bytes = fs.readFileSync(source);
const collection = JSON.parse(bytes);
const guid = '11111111-1111-4111-8111-111111111111';
const items = Object.fromEntries(collection.item.map(item => [item.name, item]));
const keys = ['captureRunId', 'captureIntent', 'rentalId', 'createdRental'];
const checks = [];
let preparedPayload;
function expect(actual) {
  const chain = {};
  chain.to = chain; chain.be = chain;
  chain.eql = expected => assert.deepEqual(actual, expected);
  chain.equal = expected => assert.equal(actual, expected);
  chain.above = expected => assert.ok(actual > expected);
  chain.an = type => assert.equal(Array.isArray(actual) ? 'array' : typeof actual, type);
  chain.deep = {equal: expected => assert.deepEqual(actual, expected)};
  Object.defineProperty(chain, 'true', {get: () => assert.equal(actual, true)});
  return chain;
}
function run(name, kind, store, options = {}) {
  const local = {...(options.local || {})};
  const env = options.env || {};
  const events = []; const assertions = [];
  const response = options.response || {code: 200, json: {}, text: ''};
  const pm = {
    collectionVariables: {get: key => store[key], set: (key, value) => {store[key] = value;}},
    variables: {
      get: key => Object.hasOwn(local, key) ? local[key] : Object.hasOwn(env, key) ? env[key] : store[key],
      set: (key, value) => {local[key] = value;},
      replaceIn: input => {assert.equal(input, '{{$guid}}'); return guid;}
    },
    execution: {skipRequest: () => events.push('skipRequest')},
    response: {code: response.code, json: () => response.json, text: () => response.text,
      to: {have: {status: expected => assert.equal(response.code, expected)}}},
    expect,
    test: (label, fn) => {try {fn(); assertions.push({name: label, passed: true});}
      catch (error) {assertions.push({name: label, passed: false, error: error.message});}}
  };
  const code = items[name].event.find(event => event.listen === kind).script.exec.join('\n');
  let error;
  try {vm.runInNewContext(code, {pm}, {timeout: 1000, filename: name + ':' + kind});}
  catch (caught) {events.push('throw'); error = caught.message;}
  return {local, events, assertions, error};
}
function check(name, fn) {
  try {fn(); checks.push({name, passed: true});}
  catch (error) {checks.push({name, passed: false, error: error.message});}
}
function validOwnership() {
  const store = Object.fromEntries(keys.map(key => [key, '']));
  const pre = run('Create rental', 'prerequest', store);
  assert.equal(pre.error, undefined);
  const payload = JSON.parse(store.captureIntent);
  const row = {...payload, id: 42};
  const post = run('Create rental', 'test', store, {response: {code: 201, json: row, text: JSON.stringify(row)}});
  assert.equal(post.error, undefined);
  assert.ok(post.assertions.every(item => item.passed));
  return store;
}
check('All saved scripts compile; no hidden sendRequest is present', () => {
  for (const item of collection.item) for (const event of item.event) {
    const source = event.script.exec.join('\n');
    new vm.Script(source);
    assert.ok(!source.includes('sendRequest'));
  }
});
check('HTTPS8702 default and all credential/run-variable defaults are unchanged or blank', () => {
  const vars = Object.fromEntries(collection.variable.map(v => [v.key, v.value]));
  assert.equal(vars.baseUrl, 'https://127.0.0.1:8702');
  for (const key of ['email','password',...keys]) assert.equal(vars[key], '');
});
check('Fresh Create persists UUID intent before any response and prepares all six fields', () => {
  const store = Object.fromEntries(keys.map(key => [key, '']));
  const result = run('Create rental','prerequest',store);
  assert.equal(result.error,undefined); assert.deepEqual(result.events,[]);
  assert.equal(store.captureRunId,guid);
  preparedPayload=JSON.parse(store.captureIntent);
  assert.deepEqual(preparedPayload, JSON.parse(result.local.createPayload));
  assert.equal(preparedPayload.description,'HW4 Postman capture run '+guid);
  assert.equal(preparedPayload.submitterEmail,'capture+'+guid+'@example.com');
  assert.equal(Object.keys(preparedPayload).length,6);
  assert.equal(store.rentalId,'');
});
for (const key of keys) check('Create refuses retained '+key+' and skips before throwing', () => {
  const store = Object.fromEntries(keys.map(k => [k, ''])); store[key] = 'retained';
  const before = JSON.stringify(store);
  const result = run('Create rental','prerequest',store);
  assert.ok(result.error); assert.deepEqual(result.events,['skipRequest','throw']);
  assert.equal(JSON.stringify(store),before);
});
check('Simulated201 saves returned ID42/row and retains intent', () => {
  const store=validOwnership(); assert.equal(store.rentalId,'42');
  assert.equal(JSON.parse(store.createdRental).id,42); assert.equal(store.captureRunId,guid);
  assert.equal(JSON.parse(store.captureIntent).description, JSON.parse(store.createdRental).description);
});
check('Simulated500 keeps uncertain intent and does not invent a returned ID', () => {
  const store=Object.fromEntries(keys.map(k=>[k,''])); run('Create rental','prerequest',store);
  const before=JSON.stringify(store);
  const result=run('Create rental','test',store,{response:{code:500,json:{detail:'offline failure'},text:''}});
  assert.equal(JSON.stringify(store),before); assert.equal(store.rentalId,'');
  assert.ok(result.assertions.some(item=>!item.passed));
});
const targets=['List rentals','Read created rental','Update created rental','Delete created rental'];
for (const name of targets) {
  check(name+': valid ownership pins exact local ID', () => {
    const store=validOwnership(); const result=run(name,'prerequest',store);
    assert.equal(result.error,undefined); assert.equal(result.local.rentalId,'42');
    if (name==='Update created rental') assert.deepEqual(Object.keys(JSON.parse(result.local.updatePayload)).sort(),['listingTitle','propertyAddress']);
  });
  for (const scope of ['env','local']) check(name+': refuses conflicting '+scope+' ID override', () => {
    const result=run(name,'prerequest',validOwnership(),{[scope]:{rentalId:'999'}});
    assert.ok(result.error); assert.deepEqual(result.events,['skipRequest','throw']);
  });
  check(name+': refuses missing ownership', () => {
    const store=validOwnership(); store.captureIntent='';
    const result=run(name,'prerequest',store); assert.ok(result.error);
    assert.deepEqual(result.events,['skipRequest','throw']);
  });
  check(name+': refuses returned-row UUID marker mismatch', () => {
    const store=validOwnership(); const row=JSON.parse(store.createdRental);
    row.description='another capture'; store.createdRental=JSON.stringify(row);
    const result=run(name,'prerequest',store); assert.ok(result.error);
    assert.deepEqual(result.events,['skipRequest','throw']);
  });
}
check('Unsafe or mismatching returned IDs are refused before a targeted request', () => {
  for (const id of [0,-1,1.5,Number.MAX_SAFE_INTEGER+1,'42']) {
    const store=validOwnership(); const row=JSON.parse(store.createdRental); row.id=id;
    store.createdRental=JSON.stringify(row); store.rentalId=String(id);
    const result=run('Delete created rental','prerequest',store);
    assert.ok(result.error); assert.deepEqual(result.events,['skipRequest','throw']);
  }
});
check('Fresh read assertions allow updated title/address while retaining immutable ownership', () => {
  const store=validOwnership(); const row={...JSON.parse(store.createdRental),listingTitle:'updated title',propertyAddress:'updated address'};
  const result=run('Read created rental','test',store,{response:{code:200,json:row,text:JSON.stringify(row)}});
  assert.equal(result.error,undefined); assert.ok(result.assertions.every(item=>item.passed));
});
check('SimulatedDELETE204 retains every run variable and blocks duplicate Create', () => {
  const store=validOwnership(); const before=JSON.stringify(store);
  const result=run('Delete created rental','test',store,{response:{code:204,json:null,text:''}});
  assert.equal(result.error,undefined); assert.ok(result.assertions.every(item=>item.passed));
  assert.equal(JSON.stringify(store),before);
  const duplicate=run('Create rental','prerequest',store);
  assert.deepEqual(duplicate.events,['skipRequest','throw']);
});
const result={
  scope:'Offline Node vm stub checks only; not Postman execution, not HTTP or MySQL evidence',
  started_at:started,finished_at:new Date().toISOString(),node_version:process.version,
  collection_path:'reports/hw04/part2/postman_collection.json',
  collection_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),
  fixture_notice:'UUID, returned ID42, statuses and responses below are synthetic stub inputs; no real request was sent.',
  prepared_payload_example:preparedPayload,
  checks,passed_checks:checks.filter(item=>item.passed).length,
  failed_checks:checks.filter(item=>!item.passed).length,
  status:checks.every(item=>item.passed)?'pass':'fail',
  network_requests:0,
  limitations:['Postman application execution and UI captures remain unverified.','Fresh manual GET ownership confirmation is still required before Update/Delete.','Operator must confirm exact-ID404 and explicitly clear only nonsecret run variables; the stub does not perform that confirmation.']
};
fs.mkdirSync(output,{recursive:true});
fs.writeFileSync(path.join(output,'collection-offline-check.json'),JSON.stringify(result,null,2)+'\n');
const summary=`OFFLINE STUB ONLY — not Postman execution.\nCollection: ${result.collection_path}\nSHA256: ${result.collection_sha256}\nStarted: ${started}\nFinished: ${result.finished_at}\n${result.passed_checks} checks passed; ${result.failed_checks} failed; 0 network requests.\nNo UI, server, database or benchmark was used. All six Part2 screenshots remain pending.\n`;
fs.writeFileSync(path.join(output,'collection-offline-check.txt'),summary);
process.stdout.write(summary);
process.exitCode=result.status==='pass'?0:1;
