<script lang="ts">import type { VocabularyEntry } from '../../api/types';import TypingPractice from './TypingPractice.svelte';import ExampleBlock from './ExampleBlock.svelte';import ExtraInfo from './ExtraInfo.svelte';import AudioButton from './AudioButton.svelte';let { entry,oncounts }=$props<{entry:VocabularyEntry;oncounts:(c:number,e:number)=>void}>();let accepted=$derived((()=>{try{return JSON.parse(entry.acceptedAnswers)as string[]}catch{return[]}})());</script>
<div class="back">
  <header class="back-word"><h2>{entry.word}</h2><div><span>{entry.ipa}</span><i>{entry.partOfSpeech}</i><AudioButton path={entry.audioPath}/></div></header>
  <section class="meaning"><span>Vietnamese meaning</span><h3>{entry.viMeaning}</h3></section>
  <section class="definition"><span>English definition</span><p>{entry.enDefinition}</p></section>
  <div class="examples"><ExampleBlock label="Meaning example" en={entry.exampleMeaningEn} vi={entry.exampleMeaningVi}/><ExampleBlock label="Usage example" en={entry.exampleUsageEn} vi={entry.exampleUsageVi}/></div>
  <TypingPractice word={entry.word} acceptedAnswers={accepted} {oncounts}/>
  <ExtraInfo {entry}/>
</div>
<style>
  .back{height:100%;padding:clamp(20px,3.2vw,36px);overflow:auto;display:grid;align-content:start;gap:17px}
  .back-word{text-align:center;padding-bottom:16px;border-bottom:1px solid var(--border)}.back-word h2{font-family:var(--font-display);font-size:clamp(31px,4.6vw,48px);line-height:1;letter-spacing:-.025em;color:#10243c}.back-word div{margin-top:9px;display:flex;align-items:center;justify-content:center;gap:10px;color:var(--text-secondary)}.back-word i{padding:4px 7px;background:var(--surface-3);border:1px solid var(--border);border-radius:4px;color:var(--accent-strong);font-size:8px;font-weight:700;font-style:normal;text-transform:uppercase;letter-spacing:.12em}
  .meaning,.definition{display:grid;gap:6px}.meaning>span,.definition>span{font-size:9px;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.15em}.meaning h3{font-size:clamp(18px,2.2vw,24px);line-height:1.3}.definition p{font-size:13px;line-height:1.55;color:var(--text-secondary)}
  .examples{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px;padding:16px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
  @media(max-width:760px){.examples{grid-template-columns:1fr}.back{gap:15px}.back-word{padding-bottom:13px}}
</style>
