import { command } from './client';import type { ImportPreview } from './types';
export const previewImport=(json:string)=>command<ImportPreview>('preview_import',{json});
export const importVocabulary=(blockId:string,json:string)=>command<{importedCount:number}>('import_vocabulary',{blockId,json});
