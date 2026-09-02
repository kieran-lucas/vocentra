import { writeFile } from 'node:fs/promises';

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

function command(method, params = {}) {
  const id = nextId++;
  const response = new Promise((resolve) => pending.set(id, resolve));
  socket.send(JSON.stringify({ id, method, params }));
  return response;
}

async function evaluate(expression) {
  const message = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (message.result?.exceptionDetails) throw new Error(message.result.exceptionDetails.text);
  return message.result?.result?.value;
}

async function waitFor(expression, timeout = 8000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${expression}`);
}

await command('Emulation.setDeviceMetricsOverride', { width: 1180, height: 760, deviceScaleFactor: 1, mobile: false });
const studyBack = process.argv.includes('--study-back');
if (studyBack) {
  await waitFor(`document.querySelectorAll('.list article').length > 0 && !([...document.querySelectorAll('button')].find(button => button.textContent.trim() === 'Study'))?.disabled`);
  await evaluate(`([...document.querySelectorAll('button')].find(button => button.textContent.trim() === 'Study'))?.click()`);
  await waitFor(`document.querySelector('.front .reveal')`);
  await evaluate(`document.querySelector('.front .reveal').click()`);
  await waitFor(`document.querySelector('.back input')`);
  await new Promise((resolve) => setTimeout(resolve, 350));
}
const result = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
const output = studyBack ? 'card-back-smoke.png' : 'light-theme-smoke.png';
await writeFile(output, Buffer.from(result.result.data, 'base64'));
socket.close();
console.log(output);
