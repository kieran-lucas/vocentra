import { command } from './client';import type { BlockSummary } from './types';
export const listBlocks=(parentId:string|null)=>command<BlockSummary[]>('list_blocks',{parentId});
export const createBlock=(parentId:string|null,name:string,iconKey:string)=>command<string>('create_block',{input:{parentId,name,iconKey}});
export const updateBlock=(id:string,name:string,iconKey:string)=>command<void>('update_block',{id,name,iconKey});
export const deleteBlock=(id:string)=>command<void>('delete_block',{id});
