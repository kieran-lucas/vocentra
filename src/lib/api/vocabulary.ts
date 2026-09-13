import { command } from './client';import type { ManagedEntry,VocabularyEntry } from './types';
export const listVocabulary=(blockId:string,search='',offset=0,limit=1000)=>command<ManagedEntry[]>('list_vocabulary',{blockId,search,offset,limit});
export const updateVocabulary=(entry:VocabularyEntry)=>command<void>('update_vocabulary',{entry});
export const removeVocabulary=(blockEntryId:string)=>command<void>('remove_vocabulary',{blockEntryId});
