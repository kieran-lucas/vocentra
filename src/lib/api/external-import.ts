import { listen } from '@tauri-apps/api/event';
import { command } from './client';
import type { ExternalImportEvent, ExternalImportSummary, SpeechProfile } from './types';

export const PROGRESS_EVENT='external-import://progress';
export const speechProfile=()=>command<SpeechProfile>('speech_profile');
export const importExternalJson=(json:string)=>command<ExternalImportSummary>('import_external_json',{json});
export const onImportProgress=(handler:(event:ExternalImportEvent)=>void)=>listen<ExternalImportEvent>(PROGRESS_EVENT,(message)=>handler(message.payload));
