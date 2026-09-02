// Drives the installed Lexium build through its own UI: opens Import JSON,
// picks a real file with DOM.setFileInputFiles, waits for the import, then
// checks the resulting cards and plays the generated pronunciation.
//
//   node scripts/release-import-smoke.mjs <batch.json> <forbidden.json>
//
// The app must already be running with --remote-debugging-port=9222.

import { resolve } from 'node:path';

const [batchArg, forbiddenArg] = process.argv.slice(2);
if (!batchArg || !forbiddenArg) throw new Error('usage: release-import-smoke.mjs <batch.json> <forbidden.json>');
const batchFile = resolve(batchArg);
const forbiddenFile = resolve(forbiddenArg);

const target = (await (await fetch('http://127.0.0.1:9222/json')).json()).find((t) => t.type === 'page');
if (!target) throw new Error('No WebView2 debug target found');

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
async function evaluate(expression) {
  const message = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (message.result?.exceptionDetails) throw new Error(message.result.exceptionDetails.exception?.description ?? 'eval failed');
  return message.result?.result?.value;
}
async function waitFor(expression, timeout = 20000, label = expression) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error(`Timed out waiting for ${label}\nDOM: ${(await evaluate('document.body.innerText')).slice(0, 900)}`);
}
// Scope clicks: while the modal is open the header's own "Import JSON" button
// still exists behind it and would win on document order.
const clickText = (text, scope = 'document') => evaluate(
  `([...${scope}.querySelectorAll('button')].find(b => b.textContent.trim().includes(${JSON.stringify(text)})))?.click()`);
const clickInDialog = (text) => clickText(text, `document.querySelector('[role="dialog"]')`);

async function attachFile(path) {
  const { result: doc } = await send('DOM.getDocument');
  const { result: node } = await send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: '.picker input[type=file]' });
  if (!node?.nodeId) throw new Error('file input not found in the import dialog');
  await send('DOM.setFileInputFiles', { nodeId: node.nodeId, files: [path] });
}

async function importFile(path) {
  await waitFor(`[...document.querySelectorAll('button')].some(b => b.textContent.includes('Import JSON'))`, 15000, 'header Import JSON');
  await clickText('Import JSON');
  await waitFor(`document.querySelector('.picker input[type=file]')`, 8000, 'import dialog');
  await attachFile(path);
  // choose() reads the file asynchronously; Import enables once the text is in.
  await waitFor(`(() => { const b = [...document.querySelectorAll('[role="dialog"] button')].find(x => x.textContent.trim() === 'Import'); return b && !b.disabled; })()`, 15000, 'file loaded');
  await clickInDialog('Import');
}

const results = {};

// ---------------------------------------------------------------- 1. valid import
await evaluate(`(() => {
  window.__audio = [];
  const Real = window.Audio;
  window.Audio = function (src) { const el = new Real(src); window.__audio.push({ src: String(src).slice(0, 40) }); const play = el.play.bind(el); el.play = () => play().then(() => { window.__audio.at(-1).played = true; }, (e) => { window.__audio.at(-1).error = String(e); }); return el; };
})()`);

await importFile(batchFile);
await waitFor(`document.querySelector('.summary') || document.querySelector('.errors')`, 180000, 'import result');
const failedText = await evaluate(`document.querySelector('.errors')?.innerText ?? ''`);
if (failedText) throw new Error(`Import reported errors: ${failedText}`);
results.firstImport = await evaluate(`(() => {
  const cells = [...document.querySelectorAll('.summary dl > div')].map(d => [d.querySelector('dt').textContent, Number(d.querySelector('dd').textContent)]);
  return { destination: document.querySelector('.summary h4').textContent, ...Object.fromEntries(cells), route: document.querySelector('.route')?.dataset.route ?? '' };
})()`);
await clickInDialog('Close');
await waitFor(`!document.querySelector('.summary')`, 8000, 'dialog closed');

// ---------------------------------------------------------------- 2. cards exist and render
await waitFor(`[...document.querySelectorAll('.tile h3')].some(n => n.textContent === 'Import Test')`, 15000, 'Import Test tile');
await evaluate(`document.querySelector('[aria-label="Open Import Test"]').click()`);
await waitFor(`[...document.querySelectorAll('.tile h3')].some(n => n.textContent === 'Release E2E')`, 10000, 'Release E2E tile');
await evaluate(`document.querySelector('[aria-label="Open Release E2E"]').click()`);
await waitFor(`document.querySelector('.manager .list article')`, 10000, 'vocabulary list');
results.cardsInBlock = await evaluate(`document.querySelectorAll('.manager .list article').length`);

await clickText('Study');
await waitFor(`document.querySelector('.front h2')`, 10000, 'study card front');
results.studyWord = await evaluate(`document.querySelector('.front h2').textContent.trim()`);
await evaluate(`document.querySelector('.front .reveal').click()`);
await waitFor(`document.querySelector('.back')`, 8000, 'card back');
results.back = await evaluate(`(() => {
  const back = document.querySelector('.back');
  return {
    ipa: back.querySelector('.back-word span')?.textContent ?? '',
    pos: back.querySelector('.back-word i')?.textContent ?? '',
    vietnamese: back.querySelector('.meaning h3')?.textContent ?? '',
    definition: back.querySelector('.definition p')?.textContent ?? '',
    examples: back.querySelectorAll('.examples > *').length,
    additional: back.querySelector('details summary')?.textContent ?? '',
    audioEnabled: Boolean(back.querySelector('[aria-label="Play pronunciation"]')),
  };
})()`);

// ---------------------------------------------------------------- 3. playback
await evaluate(`document.querySelector('.back [aria-label="Play pronunciation"]').click()`);
await waitFor(`window.__audio.length > 0`, 15000, 'audio element created');
await new Promise((r) => setTimeout(r, 1200));
results.playback = await evaluate(`window.__audio.at(-1)`);

await evaluate(`document.querySelector('[aria-label="Exit study"]')?.click()`);
await waitFor(`document.querySelector('.manager')`, 8000, 'back to manager');
await evaluate(`document.querySelector('[aria-label="Back"]').click()`);
await waitFor(`document.querySelector('nav [aria-label="Home"]')`, 8000, 'back to grid');
await evaluate(`document.querySelector('nav [aria-label="Home"]').click()`);
await waitFor(`[...document.querySelectorAll('.tile h3')].some(n => n.textContent === 'Import Test')`, 8000, 'grid');

// ---------------------------------------------------------------- 4. idempotency
await importFile(batchFile);
await waitFor(`document.querySelector('.summary') || document.querySelector('.errors')`, 180000, 'second import result');
results.secondImport = await evaluate(`(() => {
  const cells = [...document.querySelectorAll('.summary dl > div')].map(d => [d.querySelector('dt').textContent, Number(d.querySelector('dd').textContent)]);
  return Object.fromEntries(cells);
})()`);
await clickInDialog('Close');
await waitFor(`!document.querySelector('.summary')`, 8000, 'dialog closed');

// ---------------------------------------------------------------- 5. forbidden override
await importFile(forbiddenFile);
await waitFor(`document.querySelector('.errors') || document.querySelector('.summary')`, 60000, 'override result');
results.forbidden = await evaluate(`({
  rejected: Boolean(document.querySelector('.errors')),
  message: document.querySelector('.errors')?.innerText?.slice(0, 300) ?? '',
  importedAnyway: Boolean(document.querySelector('.summary')),
})`);
await clickInDialog('Cancel');

console.log(JSON.stringify(results, null, 1));
socket.close();
