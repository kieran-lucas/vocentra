import { command } from './client';import type { Rating,StudyNext,StudyStart } from './types';
export const startStudy=(blockId:string)=>command<StudyStart>('start_study',{blockId});
export const studyNext=(turnId:string)=>command<StudyNext>('study_next',{turnId});
export const rateCard=(turnId:string,rating:Rating,typingCorrect:number,typingErrors:number)=>command<void>('rate_card',{turnId,rating,typingCorrect,typingErrors});
export const rateCardAndNext=(turnId:string,rating:Rating,typingCorrect:number,typingErrors:number)=>command<StudyNext>('rate_card_and_next',{turnId,rating,typingCorrect,typingErrors});
export const endStudy=(turnId:string)=>command<void>('end_study',{turnId});
