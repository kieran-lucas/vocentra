<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { X, RotateCcw } from 'lucide-svelte';
  import type { BlockSummary, Rating, StudyNext, StudyStart } from '../../api/types';
  import { startStudy, studyNext, rateCardAndNext, endStudy } from '../../api/study';
  import { stopEntryAudio } from '../../api/audio';
  import CardShell from '../cards/CardShell.svelte';
  import RatingControls from './RatingControls.svelte';
  let { block, onexit, onerror } = $props<{block:BlockSummary;onexit:()=>void;onerror:(m:string)=>void}>();
  let session = $state<StudyStart|null>(null);
  let progress = $state<StudyNext|null>(null);
  let revealed = $state(false), busy = $state(false);
  let typingCorrect = $state(0), typingErrors = $state(0);
  let disposed = false;

  function show(next:StudyNext) {
    stopEntryAudio();
    progress = next;
    revealed = false;
    typingCorrect = 0;
    typingErrors = 0;
  }
  async function start() {
    if(busy)return;
    busy = true;
    try {
      if(session)await endStudy(session.turnId);
      if(disposed)return;
      const started = await startStudy(block.id);
      if(disposed){await endStudy(started.turnId);return}
      session = started;
      const next = await studyNext(started.turnId);
      if(!disposed)show(next);
    } catch(error) {
      if(!disposed){onerror((error as Error).message);onexit()}
    } finally { busy = false; }
  }
  async function rate(rating:Rating) {
    if(!session||!progress?.card||busy)return;
    busy = true;
    try {
      const next = await rateCardAndNext(session.turnId,rating,typingCorrect,typingErrors);
      if(!disposed)show(next);
    } catch(error) {
      if(!disposed)onerror((error as Error).message);
    } finally { busy = false; }
  }
  function keys(event:KeyboardEvent) {
    if(event.key==='Escape'){onexit();return}
    const target=event.target as HTMLElement;
    if(target.tagName==='INPUT'||target.tagName==='TEXTAREA'||event.repeat||busy)return;
    if(event.code==='Space'&&!revealed){event.preventDefault();revealed=true}
    if(revealed&&['1','2','3','4'].includes(event.key))void rate((['again','hard','good','easy'] as Rating[])[Number(event.key)-1]);
  }
  onMount(()=>{window.addEventListener('keydown',keys);void start()});
  onDestroy(()=>{
    disposed=true;
    window.removeEventListener('keydown',keys);
    stopEntryAudio();
    if(session)void endStudy(session.turnId).catch(()=>{});
  });
</script>
<section class="study"><header><button class="icon-button" aria-label="Exit study" onclick={onexit}><X size={20}/></button><div><span>Studying</span><strong>{block.name}</strong></div>{#if progress}<div class="progress-copy"><strong>{progress.uniqueCovered} / {progress.totalUnique}</strong><span>words covered · {progress.totalShown} exposures</span></div><div class="bar"><span style={`width:${progress.totalUnique?progress.uniqueCovered/progress.totalUnique*100:0}%`}></span></div>{/if}</header>{#if progress?.completed}<div class="complete"><span><RotateCcw size={28}/></span><h1>Turn complete</h1><p>You covered every word in {progress.totalShown} exposures.</p><div><button class="ghost" onclick={onexit}>Return to block</button><button class="primary" onclick={start} disabled={busy}>Study another turn</button></div></div>{:else if progress?.card}<main>{#key progress.totalShown}<CardShell entry={progress.card} {revealed} onreveal={()=>revealed=true} oncounts={(c,e)=>{typingCorrect=c;typingErrors=e}}/>{/key}</main><footer class:hidden={!revealed}><RatingControls onrate={rate} disabled={busy}/></footer>{:else}<div class="loading">Preparing your turn…</div>{/if}</section>
<style>.study{height:100vh;display:grid;grid-template-rows:76px minmax(0,1fr) 80px;padding:0 28px 12px;background:radial-gradient(circle at 50% 26%,#dceaff 0,transparent 43%),linear-gradient(180deg,#f5f8fc,var(--surface-0))}header{position:relative;display:flex;align-items:center;gap:14px;border-bottom:1px solid var(--border)}header>div:nth-child(2){display:grid}header span{font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.15em}header strong{font-family:var(--font-display)}.progress-copy{margin-left:auto;display:grid;text-align:right}.progress-copy strong{font-size:14px}.bar{position:absolute;bottom:-1px;left:0;height:2px;background:linear-gradient(90deg,var(--accent),#75a9e4);transition:width .25s}main{min-height:0;display:grid;place-items:center;padding:16px 0}footer{display:grid;place-items:center;transition:opacity .15s}.hidden{opacity:0;pointer-events:none}.complete,.loading{grid-row:2/4;display:grid;place-content:center;justify-items:center;text-align:center}.complete>span{display:grid;place-items:center;width:64px;height:64px;color:var(--success);background:var(--success-soft);border-radius:14px}.complete h1{margin-top:18px}.complete p{margin:8px 0 22px;color:var(--text-muted)}.complete div{display:flex;gap:9px}.loading{color:var(--text-muted)}</style>
