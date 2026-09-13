// Production frontend regression checks, with isolated synthetic IPC responses.
// Requires Microsoft Edge; never opens or changes the learner database.
import { createServer } from 'node:http';
import { readFile, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join, extname } from 'node:path';
import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';

const root = resolve('dist');
const server = createServer(async (request, response) => {
  try {
    const path = resolve(root, `.${new URL(request.url, 'http://localhost').pathname === '/' ? '/index.html' : new URL(request.url, 'http://localhost').pathname}`);
    if (!path.startsWith(root + '\\') && !path.startsWith(root + '/')) throw Error('Invalid path');
    response.setHeader('Content-Type', { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.jpg': 'image/jpeg' }[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const profile = await mkdtemp(join(tmpdir(), 'lexium-ui-'));
const edge = spawn(process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', [
  '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-gpu',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--window-size=1180,760', 'about:blank',
], { windowsHide: true, stdio: 'ignore' });
let socket;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  let port;
  for (let i=0; i<150; i++) {
    try { port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; } catch { await delay(100); }
  }
  if(!port) throw Error('Edge did not expose a test debug endpoint');
  const target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(target => target.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl);
  const pending = new Map(); let id=0;
  socket.onmessage = ({data}) => { const value=JSON.parse(data); if(value.id){pending.get(value.id)?.(value);pending.delete(value.id)} };
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
  async function cdp(method,params={}) {
    const current=++id;
    let timer;
    const result=new Promise((resolve,reject)=>{
      timer=setTimeout(()=>{pending.delete(current);reject(Error(`CDP timeout: ${method}`))},15000);
      pending.set(current,value=>{clearTimeout(timer);resolve(value)});
    });
    socket.send(JSON.stringify({id:current,method,params}));
    const value=await result;
    if(value.error)throw Error(JSON.stringify(value.error));
    return value.result;
  }
  async function evaluate(expression) {
    const result=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function waitFor(expression) {
    for(let i=0;i<150;i++){if(await evaluate(`Boolean(${expression})`))return;await delay(40)}
    throw Error(`Timed out: ${expression}\n${await evaluate('document.body.innerText')}`);
  }
  const click = selector => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const input = (selector,value) => evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});input.value=${JSON.stringify(value)};input.dispatchEvent(new Event('input',{bubbles:true}))})()`);
  const mock = () => {
    window.qa = { calls:[], played:[], ended:[], exposed:0, errors:[] };
    window.addEventListener('error',event=>qa.errors.push(event.message));
    window.addEventListener('unhandledrejection',event=>qa.errors.push(String(event.reason)));
    const entries = Array.from({length:1205},(_,index)=>({id:String(index),blockEntryId:String(index),word:`word${String(index).padStart(4,'0')}`,ipa:'/test/',partOfSpeech:'noun',viMeaning:'Test meaning',enDefinition:'Test definition',exampleMeaningEn:'Meaning example',exampleMeaningVi:'Translation',exampleUsageEn:'Usage example',exampleUsageVi:'Translation',masteryScore:0,totalReviews:0,acceptedAnswers:'[]',extraMetadata:'{}',collocations:'[]',wordFamily:'[]',synonyms:'[]',antonyms:'[]',audioPath:'audio/test.ogg'}));
    const result = () => ({card:entries[qa.exposed++ % entries.length],uniqueCovered:qa.exposed,totalUnique:1205,totalShown:qa.exposed,completed:false});
    window.Audio = class { pause() {} async play(){qa.played.push(this.src)} };
    window.__TAURI_INTERNALS__ = { async invoke(name,args) {
      qa.calls.push({name,args,time:performance.now()});
      if(name==='list_blocks')return Array.from({length:8},(_,index)=>({id:`block${index}`,name:`Deck ${index}`,parentId:null,iconKey:'book-open',sortOrder:index,childCount:0,wordCount:1205,averageMastery:0}));
      if(name==='list_vocabulary') {
        const search=args.search||'';
        await new Promise(resolve=>setTimeout(resolve,search==='alpha'?650:10));
        const values=search==='alpha'||search==='beta'?[{...entries[0],word:search}]:entries.filter(entry=>entry.word.includes(search));
        return values.slice(args.offset||0,(args.offset||0)+(args.limit||1000));
      }
      if(name==='start_study'){await new Promise(resolve=>setTimeout(resolve,50));return {turnId:'turn',blockName:'Deck 0',totalUnique:1205}}
      if(name==='study_next'||name==='rate_card_and_next')return result();
      if(name==='end_study'){qa.ended.push(args.turnId);return}
      if(name==='load_audio'){await new Promise(resolve=>setTimeout(resolve,20));return {mimeType:'audio/ogg',base64:'AAAA'}}
      if(name==='create_block'||name==='update_block'||name==='update_vocabulary'||name==='remove_vocabulary')return;
      throw Error(`Unexpected command: ${name}`);
    } };
  };
  await cdp('Page.enable');
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`(${mock.toString()})()`});
  await cdp('Page.navigate',{url:`http://127.0.0.1:${server.address().port}/`});
  await waitFor('document.querySelectorAll(".tile").length===8');
  console.log('Library rendered');
  const startup=await evaluate(`({ready:performance.getEntriesByName('lexium:library-ready')[0]?.startTime,scripts:performance.getEntriesByType('resource').filter(r=>r.name.endsWith('.js')).map(r=>r.name.split('/').pop())})`);
  assert(!startup.scripts.some(name=>/StudyScreen|VocabularyManager|ExternalImportDialog/.test(name)), 'Screens loaded eagerly');
  await click('[aria-label="Open Deck 0"]');
  await waitFor('document.querySelectorAll(".list article").length===100');
  console.log('Vocabulary page rendered');
  assert.equal(await evaluate('qa.calls.find(c=>c.name==="list_vocabulary").args.limit'),101);
  await click('.pagination button:last-child');
  await waitFor('document.querySelector(".word strong")?.textContent==="word0100"');
  await input('.toolbar input','alpha');
  await waitFor('qa.calls.some(c=>c.name==="list_vocabulary"&&c.args.search==="alpha")');
  await input('.toolbar input','beta');
  await waitFor('document.querySelector(".word strong")?.textContent==="beta"');
  await delay(700);
  assert.equal(await evaluate('document.querySelector(".word strong").textContent'),'beta');
  await input('.toolbar input','');
  await waitFor('document.querySelectorAll(".list article").length===100');
  await click('.header-actions .primary');
  await waitFor('document.querySelector(".front")');
  await click('[aria-label="Play pronunciation"]');
  await waitFor('qa.played.length===1');
  await click('[aria-label="Play pronunciation"]');
  await waitFor('qa.played.length===2');
  assert.equal(await evaluate('qa.calls.filter(c=>c.name==="load_audio").length'),1);
  await click('[aria-label="Reveal answer"]');
  await input('.back form input','word0000');
  await evaluate('document.querySelector(".back form").requestSubmit()');
  await waitFor('document.querySelector(".back .label small")?.textContent==="1 correct"');
  await click('.ratings .good');
  await waitFor('document.querySelector(".front")');
  const rating=await evaluate('qa.calls.find(c=>c.name==="rate_card_and_next")');
  assert.equal(rating.args.typingCorrect,1);
  assert.equal(await evaluate('qa.calls.filter(c=>c.name==="study_next").length'),1);
  await click('[aria-label="Reveal answer"]');
  assert.equal(await evaluate('document.querySelector(".back .label small").textContent'),'0 correct');
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await click('.ratings .good');
  await waitFor('document.querySelector(".front")');
  assert.equal(await evaluate('document.querySelector(".study main .shell").getAnimations().length'),0);
  await click('[aria-label="Exit study"]');
  await waitFor('qa.ended.length>0&&document.querySelector(".manager")');
  await click('[aria-label="Home"]');
  await waitFor('document.querySelector(".app-header .primary")');
  await click('.app-header .primary');
  await waitFor('document.querySelector("[role=dialog]")');
  await click('[aria-label="Close"]');
  assert.deepEqual(await evaluate('qa.errors'),[]);
  const screenshot=await cdp('Page.captureScreenshot',{format:'png'});
  await writeFile('src-tauri/target/performance-ui.png',Buffer.from(screenshot.data,'base64'));
  console.log(JSON.stringify({startup,pagination:true,searchRace:true,audioCache:true,singleRatingIPC:true,typingReset:true,reducedMotion:true,sessionCleanup:true,lazyDialog:true,errors:[]},null,2));
} finally {
  socket?.close();
  edge.kill();
  server.close();
}
