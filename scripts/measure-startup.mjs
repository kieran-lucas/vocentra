// Launch a release binary and measure process-to-visible-library and WebView
// paint timing. Only reads the library; normal startup migrations still run.
import { spawn } from 'node:child_process';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const [executable,label='current',sampleCount='3']=process.argv.slice(2);
if(!executable)throw Error('Usage: node scripts/measure-startup.mjs <exe> <label> [samples]');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const samples=[];
for(let iteration=0;iteration<Number(sampleCount);iteration++) {
  const port=19000+Math.floor(Math.random()*20000);
  const started=performance.now();
  const app=spawn(resolve(executable),[],{windowsHide:true,stdio:'ignore',env:{...process.env,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`}});
  let socket;
  try {
    let target;
    const deadline=Date.now()+30000;
    while(Date.now()<deadline) {
      try { target=(await (await fetch(`http://127.0.0.1:${port}/json`,{signal:AbortSignal.timeout(500)})).json()).find(t=>t.type==='page'); if(target)break; } catch {}
      if(app.exitCode!==null)throw Error(`App exited: ${app.exitCode}`);
      await delay(30);
    }
    if(!target)throw Error('No WebView debug target');
    socket=new WebSocket(target.webSocketDebuggerUrl);
    const pending=new Map();let id=0;
    socket.onmessage=({data})=>{const result=JSON.parse(data);pending.get(result.id)?.(result);pending.delete(result.id)};
    await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
    async function cdp(method,params={}) {
      const current=++id;let timer;
      const result=new Promise((resolve,reject)=>{timer=setTimeout(()=>reject(Error(`Timed out: ${method}`)),5000);pending.set(current,value=>{clearTimeout(timer);resolve(value)})});
      socket.send(JSON.stringify({id:current,method,params}));return await result;
    }
    let state;
    while(Date.now()<deadline) {
      const result=await cdp('Runtime.evaluate',{expression:`(()=>{const grid=document.querySelector('.grid,.empty');if(!grid||Number(getComputedStyle(grid.parentElement).opacity)<.99)return null;return {ready:performance.getEntriesByName('lexium:library-ready')[0]?.startTime??null,fcp:performance.getEntriesByName('first-contentful-paint')[0]?.startTime??null,tiles:document.querySelectorAll('.tile').length}})()`,returnByValue:true});
      state=result.result?.result?.value;
      if(state)break;
      await delay(20);
    }
    if(!state)throw Error('Library did not become visible');
    samples.push({processToLibraryMs:Math.round(performance.now()-started),...state});
    if(iteration===0&&label==='optimized') {
      const screenshot=await cdp('Page.captureScreenshot',{format:'png'});
      await writeFile('src-tauri/target/installed-app.png',Buffer.from(screenshot.result.data,'base64'));
    }
  } finally {
    socket?.close();
    if(app.exitCode===null){const exited=new Promise(resolve=>app.once('exit',resolve));app.kill();await exited}
  }
  await delay(250);
}
const median=values=>values.sort((a,b)=>a-b)[Math.floor(values.length/2)];
const report={label,executable:resolve(executable),samples,medianProcessToLibraryMs:median(samples.map(s=>s.processToLibraryMs)),medianFcpMs:median(samples.map(s=>s.fcp))};
await writeFile(`src-tauri/target/startup-${label}.json`,JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));
