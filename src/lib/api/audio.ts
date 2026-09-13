import { command } from './client';

type AudioPayload = { mimeType:string; base64:string };
let active:HTMLAudioElement|null=null;
let playbackVersion=0;
const cache=new Map<string,string>();
const pending=new Map<string,Promise<string>>();
const maxCacheBytes=2*1024*1024;
let cacheBytes=0;
let cacheGeneration=0;

function audioSource(relativePath:string):Promise<string>{
  const cached=cache.get(relativePath);
  if(cached){cache.delete(relativePath);cache.set(relativePath,cached);return Promise.resolve(cached)}
  const existing=pending.get(relativePath);
  if(existing)return existing;
  const generation=cacheGeneration;
  const request=command<AudioPayload>('load_audio',{relativePath}).then(payload=>{
    const source=`data:${payload.mimeType};base64,${payload.base64}`;
    if(generation===cacheGeneration&&source.length<=maxCacheBytes){
      while(cache.size&&(cacheBytes+source.length>maxCacheBytes||cache.size>=24)){
        const oldest=cache.keys().next().value!;
        cacheBytes-=cache.get(oldest)!.length;
        cache.delete(oldest);
      }
      cache.set(relativePath,source);
      cacheBytes+=source.length;
    }
    return source;
  }).finally(()=>{if(pending.get(relativePath)===request)pending.delete(relativePath)});
  pending.set(relativePath,request);
  return request;
}

export function stopEntryAudio(){
  ++playbackVersion;
  active?.pause();
}

export function clearAudioCache(){
  ++cacheGeneration;
  cache.clear();
  pending.clear();
  cacheBytes=0;
}

export async function playEntryAudio(relativePath:string):Promise<void>{
  stopEntryAudio();
  const version=playbackVersion;
  const source=await audioSource(relativePath);
  if(version!==playbackVersion)return;
  active??=new Audio();
  active.src=source;
  await active.play();
}
