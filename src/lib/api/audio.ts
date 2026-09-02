import { command } from './client';

type AudioPayload = { mimeType:string; base64:string };
let active:HTMLAudioElement|null=null;

export async function playEntryAudio(relativePath:string):Promise<void>{
  active?.pause();
  const payload=await command<AudioPayload>('load_audio',{relativePath});
  active=new Audio(`data:${payload.mimeType};base64,${payload.base64}`);
  await active.play();
}
