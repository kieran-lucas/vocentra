const target = (await (await fetch('http://127.0.0.1:9222/json')).json())[0];
if (!target) throw new Error('No WebView2 debug target found');

const socket = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
const runtimeErrors = [];
let nextId = 1;
socket.onmessage = ({ data }) => {
  const message = JSON.parse(data);
  if (message.method === 'Runtime.exceptionThrown' || message.method === 'Log.entryAdded') runtimeErrors.push(message.params);
  if (message.id && pending.has(message.id)) {
    pending.get(message.id)(message);
    pending.delete(message.id);
  }
};
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
socket.send(JSON.stringify({ id: nextId++, method: 'Runtime.enable' }));
socket.send(JSON.stringify({ id: nextId++, method: 'Log.enable' }));

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
  throw new Error(`Timed out waiting for ${expression}; body=${body}; runtime=${JSON.stringify(runtimeErrors)}`);
}

if (!await evaluate(`document.querySelector('.manager')?.innerText.includes('A1 Pilot')`)) {
  await evaluate(`document.querySelector('[aria-label="Open Oxford 5000"]')?.click()`);
  await waitFor(`document.querySelector('.manager') || [...document.querySelectorAll('.tile h3')].some(node => node.textContent === 'A1 Pilot')`);
  if (!await evaluate(`document.querySelector('.manager')`)) {
    const leafText = await evaluate(`document.querySelector('[aria-label="Open A1 Pilot"]')?.closest('.tile')?.innerText`);
    if (!leafText?.includes('180 words')) throw new Error(`Unexpected pilot tile: ${leafText}`);
    await evaluate(`document.querySelector('[aria-label="Open A1 Pilot"]')?.click()`);
  }
}
await waitFor(`document.querySelector('.manager')`);
const managerText = await evaluate(`document.querySelector('.manager').innerText`);
if (!managerText.includes('A1 Pilot')) throw new Error('Pilot manager did not open');
await waitFor(`document.querySelectorAll('.list article').length === 180`);
await evaluate(`([...document.querySelectorAll('button')].find(button => button.textContent.trim() === 'Study'))?.click()`);
await waitFor(`document.querySelector('.front')`);
const audioReady = await evaluate(`Boolean(document.querySelector('.front button[title="Play pronunciation"]:not(:disabled)'))`);
if (!audioReady) throw new Error('Local pronunciation control is unavailable');
await evaluate(`document.querySelector('.front button[title="Play pronunciation"]')?.click()`);
await new Promise((resolve) => setTimeout(resolve, 800));
await evaluate(`document.querySelector('.front .reveal')?.click()`);
await waitFor(`document.querySelector('.back input')`);
const backText = await evaluate(`document.querySelector('.back').innerText.toLowerCase()`);
if (!backText.includes('vietnamese meaning') || !backText.includes('english definition')) throw new Error('Card back is incomplete');
if (!backText.includes('more language notes')) throw new Error('Card back is missing the final notes section');
await evaluate(`document.querySelector('[aria-label="Exit study"]')?.click()`);
await waitFor(`document.querySelector('.manager')`);
await waitFor(`document.querySelectorAll('.list article').length === 180 && !([...document.querySelectorAll('button')].find(button => button.textContent.trim() === 'Study'))?.disabled`);
await evaluate(`([...document.querySelectorAll('button')].find(button => button.textContent.trim() === 'Study'))?.click()`);
await waitFor(`document.querySelector('.front .reveal')`);
await evaluate(`document.querySelector('.front .reveal')?.click()`);
await waitFor(`document.querySelector('.back input')`);
await evaluate(`document.querySelector('[aria-label="Exit study"]')?.click()`);
await waitFor(`document.querySelector('.manager')`);
console.log(JSON.stringify({ pilotRootVisible: true, pilotLeafVisible: true, pilotLeafOpens: true, importedWords: 180, localAudioControl: true, cardBackComplete: true, secondStudyStarts: true }));
socket.close();
