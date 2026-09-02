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
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
async function evaluate(expression) {
  const id = nextId++;
  const response = new Promise((resolve) => pending.set(id, resolve));
  socket.send(JSON.stringify({ id, method: 'Runtime.evaluate', params: { expression, awaitPromise: true, returnByValue: true } }));
  return (await response).result?.result?.value;
}
async function waitFor(expression, timeout = 10000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out: ${expression}`);
}
await evaluate(`document.querySelector('[aria-label="Home"]')?.click()`);
await waitFor(`document.querySelector('[aria-label="Open Oxford 5000"]')`);
await evaluate(`document.querySelector('[aria-label="Open Oxford 5000"]')?.click()`);
await waitFor(`document.querySelector('[aria-label="Open A1 Pilot"]')`);
await evaluate(`(() => { const tile=[...document.querySelectorAll('.tile')].find(node=>node.querySelector('h3')?.textContent==='A1 Pilot'); tile?.querySelector('[aria-label="Block actions"]')?.click(); })()`);
await waitFor(`document.querySelector('.tile .menu')?.textContent.includes('Import vocabulary')`);
await evaluate(`([...document.querySelectorAll('.tile .menu button')].find(button => button.textContent.includes('Import vocabulary')))?.click()`);
await waitFor(`document.querySelector('[role="dialog"] .picker')`);
console.log('Oxford 5000 / A1 Pilot / Import vocabulary opened');
socket.close();
