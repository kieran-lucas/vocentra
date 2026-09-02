// Installed-build acceptance for leaf-owned V2 import.
// The installed app must be running with WebView2 remote debugging on port 9222.

import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const [batchArg, legacyArg, mode] = process.argv.slice(2);
if (!batchArg || !legacyArg) throw new Error('usage: release-import-smoke.mjs <v2.json> <v1.json> [--restart-check]');
const batchFile = resolve(batchArg);
const legacyFile = resolve(legacyArg);
const batchJson = await readFile(batchFile, 'utf8');
const restartOnly = mode === '--restart-check';

const target = (await (await fetch('http://127.0.0.1:9222/json')).json()).find((item) => item.type === 'page');
if (!target) throw new Error('No installed WebView2 debug target found');
const socket = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
let nextId = 1;
socket.onmessage = ({ data }) => {
  const message = JSON.parse(data);
  if (message.id && pending.has(message.id)) {
    pending.get(message.id)(message);
    pending.delete(message.id);
  }
};
await new Promise((ok, fail) => { socket.onopen = ok; socket.onerror = fail; });

function send(method, params = {}) {
  const id = nextId++;
  const response = new Promise((ok) => pending.set(id, ok));
  socket.send(JSON.stringify({ id, method, params }));
  return response;
}
function assert(condition, message) {
  if (!condition) throw new Error(`Acceptance assertion failed: ${message}`);
}
async function evaluate(expression) {
  const message = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (message.result?.exceptionDetails) throw new Error(message.result.exceptionDetails.exception?.description ?? 'eval failed');
  return message.result?.result?.value;
}
async function waitFor(expression, timeout = 20000, label = expression) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await new Promise((done) => setTimeout(done, 150));
  }
  throw new Error(`Timed out waiting for ${label}\nDOM: ${(await evaluate('document.body.innerText')).slice(0, 1200)}`);
}
const clickText = (text, scope = 'document') => evaluate(
  `([...${scope}.querySelectorAll('button')].find(button => button.textContent.trim().includes(${JSON.stringify(text)})))?.click()`);
const clickDialog = (text) => clickText(text, `document.querySelector('[role="dialog"]')`);
const setValue = (selector, value) => evaluate(`(() => { const element=document.querySelector(${JSON.stringify(selector)}); const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element),'value').set; setter.call(element,${JSON.stringify(value)}); element.dispatchEvent(new Event('input',{bubbles:true})); })()`);

async function attachFile(path) {
  const { result: document } = await send('DOM.getDocument');
  const { result: node } = await send('DOM.querySelector', { nodeId: document.root.nodeId, selector: '.picker input[type=file]' });
  if (!node?.nodeId) throw new Error('file input not found');
  await send('DOM.setFileInputFiles', { nodeId: node.nodeId, files: [path] });
}
async function home() {
  await evaluate(`document.querySelector('[aria-label="Home"]')?.click()`);
  await waitFor(`document.querySelector('.app-header')`, 10000, 'library home');
}
async function tileExists(name) {
  return evaluate(`[...document.querySelectorAll('.tile h3')].some(node => node.textContent === ${JSON.stringify(name)})`);
}
async function openTile(name) {
  await evaluate(`document.querySelector(${JSON.stringify(`[aria-label="Open ${name}"]`)})?.click()`);
}
async function openOptions(name) {
  await evaluate(`(() => { const tile=[...document.querySelectorAll('.tile')].find(node=>node.querySelector('h3')?.textContent===${JSON.stringify(name)}); tile?.querySelector('[aria-label="Block actions"]')?.click(); })()`);
  await waitFor(`document.querySelector('.tile .menu')`, 5000, `${name} options`);
}
async function createBlock(name) {
  await clickText('New block');
  await waitFor(`document.querySelector('[role="dialog"] input')`, 5000, 'create block dialog');
  await setValue('[role="dialog"] input', name);
  await clickDialog('Save block');
  await waitFor(`[...document.querySelectorAll('.tile h3')].some(node=>node.textContent===${JSON.stringify(name)})`, 10000, `${name} tile`);
}
async function ensureHierarchy() {
  await home();
  if (!await tileExists('Import Test')) await createBlock('Import Test');
  await openTile('Import Test');
  await waitFor(`document.querySelector('.app-header')`, 10000, 'Import Test collection');
  if (!await tileExists('V2 Leaf A')) await createBlock('V2 Leaf A');
  if (!await tileExists('V2 Leaf B')) await createBlock('V2 Leaf B');
  if (!await tileExists('V2 Parent')) await createBlock('V2 Parent');
  const parentHasChild = await evaluate(`([...document.querySelectorAll('.tile')].find(node=>node.querySelector('h3')?.textContent==='V2 Parent')?.textContent??'').includes('sub-block')`);
  if (!parentHasChild) {
    await openOptions('V2 Parent');
    await clickText('Add child', `document.querySelector('.tile .menu')`);
    await waitFor(`document.querySelector('[role="dialog"] input')`, 5000, 'child dialog');
    await setValue('[role="dialog"] input', `Child ${Date.now()}`);
    await clickDialog('Save block');
    await waitFor(`!document.querySelector('[role="dialog"]')`, 8000, 'child created');
  }
}
async function importFromLeaf(name, path) {
  await openOptions(name);
  await waitFor(`document.querySelector('.tile .menu')?.textContent.includes('Import vocabulary')`, 5000, `${name} import action`);
  await clickText('Import vocabulary', `document.querySelector('.tile .menu')`);
  await waitFor(`document.querySelector('.picker input[type=file]')`, 8000, 'V2 import dialog');
  await attachFile(path);
  await waitFor(`(() => { const button=[...document.querySelectorAll('[role="dialog"] button')].find(node=>node.textContent.trim()==='Import'); return button&&!button.disabled; })()`, 15000, 'file loaded');
  await clickDialog('Import');
  await waitFor(`document.querySelector('.summary') || document.querySelector('.errors')`, 240000, 'import result');
  const error = await evaluate(`document.querySelector('.errors')?.innerText ?? ''`);
  if (error) throw new Error(`Import failed: ${error}`);
  const result = await evaluate(`(() => ({ destination:document.querySelector('.summary h4').textContent,...Object.fromEntries([...document.querySelectorAll('.summary dl>div')].map(row=>[row.querySelector('dt').textContent,Number(row.querySelector('dd').textContent)])),route:document.querySelector('.route')?.dataset.route??'' }))()`);
  await clickDialog('Close');
  await waitFor(`!document.querySelector('[role="dialog"]')`, 8000, 'import dialog closed');
  return result;
}

const results = {};
await ensureHierarchy();
if (restartOnly) {
  await openTile('V2 Leaf A');
  await waitFor(`document.querySelector('.manager .list article')`, 12000, 'persisted Leaf A cards');
  results.restartLeafACards = await evaluate(`document.querySelectorAll('.manager .list article').length`);
  await evaluate(`document.querySelector('[aria-label="Back"]')?.click()`);
  await waitFor(`document.querySelector('.app-header')`, 8000, 'back to Import Test');
  await openTile('V2 Leaf B');
  await waitFor(`document.querySelector('.manager .list article')`, 12000, 'persisted Leaf B cards');
  results.restartLeafBCards = await evaluate(`document.querySelectorAll('.manager .list article').length`);
  assert(results.restartLeafACards >= 2, 'Leaf A cards did not persist after restart');
  assert(results.restartLeafBCards >= 2, 'Leaf B cards did not persist after restart');
  console.log(JSON.stringify(results, null, 2));
  socket.close();
  process.exit(0);
}

await evaluate(`(() => {
  window.__v2Audio = [];
  const NativeAudio = window.Audio;
  window.Audio = function (src) {
    const element = new NativeAudio(src);
    const event = { src: String(src).slice(0, 48), played: false, error: '' };
    window.__v2Audio.push(event);
    const nativePlay = element.play.bind(element);
    element.play = () => nativePlay().then(
      () => { event.played = true; },
      (error) => { event.error = String(error); throw error; },
    );
    return element;
  };
  window.Audio.prototype = NativeAudio.prototype;
})()`);

results.leafAFirst = await importFromLeaf('V2 Leaf A', batchFile);
results.leafARepeat = await importFromLeaf('V2 Leaf A', batchFile);
results.leafB = await importFromLeaf('V2 Leaf B', batchFile);

assert(results.leafAFirst.destination.endsWith('Import Test / V2 Leaf A'), 'first import used the wrong destination');
const leafAWasFresh = results.leafAFirst.Added === 2;
assert(
  leafAWasFresh
    ? results.leafAFirst.Reused === 0 && results.leafAFirst['Already in block'] === 0
    : results.leafAFirst.Added === 0 && results.leafAFirst.Reused === 0 && results.leafAFirst['Already in block'] === 2,
  'Leaf A classification is neither a fresh 2 NEW import nor a safe rerun',
);
assert(
  leafAWasFresh
    ? results.leafAFirst['Audio generated'] === 2 && results.leafAFirst['Audio reused'] === 0
    : results.leafAFirst['Audio generated'] === 0,
  'Leaf A audio plan is wrong',
);
assert(results.leafAFirst.Conflicts === 0 && results.leafAFirst.Failed === 0, 'fresh Leaf A import has conflicts or failures');
assert(results.leafAFirst.route.startsWith('sidecar'), 'installed app did not use its packaged sidecar');

assert(results.leafARepeat.Added === 0 && results.leafARepeat.Reused === 0 && results.leafARepeat['Already in block'] === 2, 'same-block reimport is not idempotent');
assert(results.leafARepeat['Audio generated'] === 0, 'same-block reimport regenerated audio');
assert(results.leafARepeat.Conflicts === 0 && results.leafARepeat.Failed === 0, 'same-block reimport has conflicts or failures');

const leafBWasNewMembership = results.leafB.Reused === 2;
assert(
  results.leafB.Added === 0 && (leafBWasNewMembership
    ? results.leafB['Already in block'] === 0
    : results.leafB.Reused === 0 && results.leafB['Already in block'] === 2),
  'Leaf B is neither a 2 REUSE_GLOBAL import nor a safe rerun',
);
assert(results.leafB['Audio generated'] === 0 && (!leafBWasNewMembership || results.leafB['Audio reused'] === 2), 'second leaf did not reuse current audio');
assert(results.leafB.Conflicts === 0 && results.leafB.Failed === 0, 'second-leaf import has conflicts or failures');

await openOptions('V2 Parent');
results.nonLeafActionAbsent = !await evaluate(`document.querySelector('.tile .menu')?.textContent.includes('Import vocabulary')`);
const ids = await evaluate(`window.__TAURI_INTERNALS__.invoke('list_blocks',{parentId:null}).then(async roots => { const root=roots.find(block=>block.name==='Import Test'); const children=await window.__TAURI_INTERNALS__.invoke('list_blocks',{parentId:root.id}); return Object.fromEntries(children.map(block=>[block.name,block.id])); })`);
results.forcedNonLeaf = await evaluate(`window.__TAURI_INTERNALS__.invoke('import_external_json',{json:${JSON.stringify(batchJson)},targetBlockId:${JSON.stringify(ids['V2 Parent'])}}).then(()=>({rejected:false}),error=>({rejected:true,message:typeof error==='string'?error:JSON.stringify(error)}))`);
assert(results.nonLeafActionAbsent, 'non-leaf menu exposes Import vocabulary');
assert(results.forcedNonLeaf.rejected && /leaf|child/i.test(results.forcedNonLeaf.message), 'forced non-leaf backend call was not rejected');

results.v1 = await (async () => {
  await importFromLeaf('V2 Leaf A', legacyFile).then(() => { throw new Error('V1 unexpectedly imported'); }, () => {});
  return evaluate(`({rejected:Boolean(document.querySelector('.errors')),message:document.querySelector('.errors')?.innerText??''})`);
})();
assert(results.v1.rejected && /schema v1|schemaVersion|schema v2/i.test(results.v1.message), 'V1 file was not cleanly rejected');

await evaluate(`document.querySelector('[role="dialog"] button.ghost')?.click()`);
await openTile('V2 Leaf A');
await waitFor(`document.querySelector('.manager .list article')`, 10000, 'Leaf A cards');
results.leafACards = await evaluate(`document.querySelectorAll('.manager .list article').length`);
await clickText('Study');
await waitFor(`document.querySelector('.front h2')`, 10000, 'study card');
await evaluate(`document.querySelector('.front .reveal').click()`);
await waitFor(`document.querySelector('.back [aria-label="Play pronunciation"]')`, 10000, 'audio control');
results.audioControl = true;
await evaluate(`document.querySelector('.back [aria-label="Play pronunciation"]').click()`);
await waitFor(`window.__v2Audio.length > 0`, 15000, 'audio element creation');
await waitFor(`window.__v2Audio.at(-1).played || window.__v2Audio.at(-1).error`, 15000, 'audio playback');
results.playback = await evaluate(`window.__v2Audio.at(-1)`);
assert(results.playback.played && !results.playback.error, `pronunciation did not play: ${results.playback.error}`);

console.log(JSON.stringify(results, null, 2));
socket.close();
