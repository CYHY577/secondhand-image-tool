const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('index.html', 'utf8');
for (const file of ['index.html', 'admin.html']) {
  const source = fs.readFileSync(file, 'utf8');
  for (const [, script] of source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) {
    new vm.Script(script, { filename: file });
  }
  assert.equal((source.match(/id="cfg-proxy-url"/g) || []).length, 1);
}
const routing = html.slice(html.indexOf('let localProxyAvailable;'), html.indexOf('async function callWanAPI'));
function context(protocol, hostname, settings = {}, health = true) {
  return vm.createContext({ URL, location: {protocol, hostname},
    LS: {USE_PROXY:'enabled', PROXY_URL:'proxy'},
    localStorage: { getItem: key => settings[key] },
    fetch: async () => ({ok:health, json:async () => ({service:'secondhand-local-proxy'})})
  });
}
async function route(ctx) {
  vm.runInContext(routing, ctx);
  return vm.runInContext("applyProxy('https://dashscope.aliyuncs.com/api/v1/tasks/abc')", ctx);
}
(async () => {
  assert.equal(await route(context('http:', 'localhost', {enabled:'true'})), '/api/dashscope/api/v1/tasks/abc');
  assert.equal(await route(context('https:', 'example.com')), 'https://dashscope.aliyuncs.com/api/v1/tasks/abc');
  assert.match(await route(context('https:', 'example.com', {enabled:'true',proxy:'https://own-worker.example/'})), /^https:\/\/own-worker.example\/\?/);
  await assert.rejects(() => route(context('file:', '', {enabled:'true'})), /没有填写地址/);
  await assert.rejects(() => route(context('https:', 'example.com', {enabled:'true',proxy:'http://insecure.example/'})), /HTTPS/);
  const elements = {};
  let debug;
  let rendered = false;
  const generationContext = vm.createContext({
    state: {pendingSimFail:false}, LS:{API_KEY:'key',MODEL:'model'},
    localStorage:{getItem:key => key === 'key' ? 'test-placeholder' : null},
    $: id => elements[id] ||= {value:'test item',style:{},classList:{add(){},remove(){}}},
    buildPrompt:() => 'test', resetSteps(){}, setStepActive(){},setStepDone(){},setStepError(){},
    showErrorBanner(){}, elapsed:() => '0s', rand:() => 0, sleep:async () => {},
    callWanAPI:async () => {throw new Error('test network failure');},
    renderResult:() => {rendered=true;}, saveDebug:value => {debug=value;}
  });
  vm.runInContext(html.slice(html.indexOf('async function runGeneration()'), html.indexOf('function openSettings()')), generationContext);
  await vm.runInContext('runGeneration()', generationContext);
  assert.equal(rendered, false);
  assert.equal(debug.gen.status, 'api_fail');
  assert.equal(elements['error-detail'].textContent, 'test network failure');
  assert.equal(elements['btn-generate'].disabled, false);
  assert.equal(generationContext.state.isGenerating, false);
  console.log('Client syntax, configuration fields and 5 routing cases passed.');
  console.log('Failed API stops generation, records the error and enables retry.');
})().catch(error => { console.error(error); process.exitCode = 1; });
