import { invoke } from '@tauri-apps/api/core';

export async function command<T>(name:string,args:Record<string,unknown>={}):Promise<T>{
  try { return await invoke<T>(name,args); }
  catch (error) {
    if (typeof error === 'object' && error && 'message' in error) throw new Error(String((error as {message:unknown}).message));
    throw new Error(typeof error === 'string' ? error : 'An unexpected application error occurred');
  }
}
