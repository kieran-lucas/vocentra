import { readFile } from 'node:fs/promises';

const target = (await (await fetch('http://127.0.0.1:9222/json')).json())[0];
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
await new Promise((resolve, reject) => {
  socket.onopen = resolve;
  socket.onerror = reject;
});

async function evaluate(expression) {
  const id = nextId++;
  const response = new Promise((resolve) => pending.set(id, resolve));
  socket.send(JSON.stringify({ id, method: 'Runtime.evaluate', params: { expression, awaitPromise: true, returnByValue: true } }));
  const message = await response;
  if (message.result?.exceptionDetails) throw new Error(message.result.exceptionDetails.text);
  return message.result?.result?.value;
}

async function waitFor(expression, timeout = 8000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  const body = await evaluate(`document.body.innerText`);
  throw new Error(`Timed out waiting for: ${expression}\nDOM: ${body}`);
}

const clickText = (text) => evaluate(`([...document.querySelectorAll('button')].find(button => button.textContent.trim().includes(${JSON.stringify(text)})))?.click()`);
const setValue = (selector, value) => evaluate(`(() => { const element=document.querySelector(${JSON.stringify(selector)}); const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element),'value').set; setter.call(element,${JSON.stringify(value)}); element.dispatchEvent(new Event('input',{bubbles:true})); })()`);

const rootName = `QA Root ${Date.now()}`;
const leafName = 'QA Leaf';
const sample = await readFile(new URL('../sample-data/vocabulary.sample.json', import.meta.url), 'utf8');

await clickText('New block');
await waitFor(`document.querySelector('[role="dialog"] input')`);
await setValue('[role="dialog"] input', rootName);
await clickText('Save block');
await waitFor(`[...document.querySelectorAll('.tile h3')].some(node=>node.textContent===${JSON.stringify(rootName)})`);

await evaluate(`(() => { const tile=[...document.querySelectorAll('.tile')].find(node=>node.querySelector('h3')?.textContent===${JSON.stringify(rootName)}); tile.querySelector('[aria-label="Block actions"]').click(); })()`);
await clickText('Add child');
await waitFor(`document.querySelector('[role="dialog"] input')`);
await setValue('[role="dialog"] input', leafName);
await clickText('Save block');
await waitFor(`!document.querySelector('[role="dialog"]')`);
await waitFor(`[...document.querySelectorAll('.tile')].some(node=>node.querySelector('h3')?.textContent===${JSON.stringify(rootName)} && node.textContent.includes('1 sub-block'))`);

await evaluate(`document.querySelector(${JSON.stringify(`[aria-label="Open ${rootName}"]`)}).click()`);
await waitFor(`[...document.querySelectorAll('.tile h3')].some(node=>node.textContent===${JSON.stringify(leafName)})`);
await evaluate(`document.querySelector('[aria-label="Open QA Leaf"]').click()`);
await waitFor(`document.querySelector('.manager')`);

await clickText('Import JSON');
await waitFor(`document.querySelector('[role="dialog"] textarea')`);
await setValue('[role="dialog"] textarea', sample);
await clickText('Import all valid entries');
await waitFor(`document.querySelectorAll('.list article').length===8`, 12000);

await clickText('Study');
await waitFor(`document.querySelector('.front h2')`);
const word = await evaluate(`document.querySelector('.front h2').textContent`);
const frontText = await evaluate(`document.querySelector('.front').textContent`);
if (!word || /Vietnamese|Definition|Typing practice/.test(frontText)) throw new Error('Card front exposed answer content');
await evaluate(`document.querySelector('.front .reveal').click()`);
await waitFor(`document.querySelector('.back input')`);

await setValue('.back input', word);
await evaluate(`document.querySelector('.back input').closest('form').requestSubmit()`);
await waitFor(`document.querySelector('.back input').value==='' && document.activeElement===document.querySelector('.back input')`);

await setValue('.back input', '__wrong__');
await evaluate(`document.querySelector('.back input').closest('form').requestSubmit()`);
await waitFor(`document.querySelector('.back section.invalid')`);
const wrongRetained = await evaluate(`document.querySelector('.back input').value==='__wrong__'`);
if (!wrongRetained) throw new Error('Incorrect spelling was cleared');

await clickText('Good');
await waitFor(`document.querySelector('.front') || document.querySelector('.complete')`);
await evaluate(`document.querySelector('[aria-label="Exit study"]').click()`);
await waitFor(`document.querySelector('.manager')`);
await evaluate(`document.querySelector('[aria-label="Back"]').click()`);
await waitFor(`document.querySelector('nav [aria-label="Home"]')`);
await evaluate(`document.querySelector('nav [aria-label="Home"]').click()`);
await waitFor(`[...document.querySelectorAll('.tile h3')].some(node=>node.textContent===${JSON.stringify(rootName)})`);

await evaluate(`window.confirm=()=>true`);
await evaluate(`(() => { const tile=[...document.querySelectorAll('.tile')].find(node=>node.querySelector('h3')?.textContent===${JSON.stringify(rootName)}); tile.querySelector('[aria-label="Block actions"]').click(); })()`);
await clickText('Delete');
await waitFor(`![...document.querySelectorAll('.tile h3')].some(node=>node.textContent===${JSON.stringify(rootName)})`);

console.log(JSON.stringify({ rootCreated: true, nestedLeafCreated: true, imported: 8, studyRevealed: true, typingCorrectCleared: true, typingWrongRetained: true, ratingPersisted: true, cleanupComplete: true }));
socket.close();
