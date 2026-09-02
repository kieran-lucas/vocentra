<script lang="ts">
  import { ArrowLeft, ArrowRight, Home, Search, Trash2, Pencil, BookOpen } from 'lucide-svelte';
  import type { BlockSummary, ManagedEntry, VocabularyEntry } from '../../api/types';
  import { listVocabulary, removeVocabulary, updateVocabulary } from '../../api/vocabulary';
  import Modal from '../common/Modal.svelte';

  let {
    block, onback, onforward, onhome, canback, canforward, onstudy, onchange, onerror
  } = $props<{
    block: BlockSummary;
    onback: () => void;
    onforward: () => void;
    onhome: () => void;
    canback: boolean;
    canforward: boolean;
    onstudy: () => void;
    onchange: () => void;
    onerror: (message: string) => void;
  }>();

  let entries = $state<ManagedEntry[]>([]);
  let search = $state('');
  let editing = $state<ManagedEntry | null>(null);

  async function load() {
    try { entries = await listVocabulary(block.id, search); }
    catch(error) { onerror((error as Error).message); }
  }
  $effect(() => {
    search;
    const timer = setTimeout(load, 180);
    return () => clearTimeout(timer);
  });
  async function remove(entry: ManagedEntry) {
    if(!confirm(`Remove “${entry.word}” from this block?`)) return;
    await removeVocabulary(entry.blockEntryId);
    await load();
    onchange();
  }
  async function save() {
    if(!editing) return;
    await updateVocabulary(editing as VocabularyEntry);
    editing = null;
    await load();
  }
</script>

<section class="manager">
  <header>
    <div class="navigation-controls">
      <button class="icon-button" aria-label="Back" title="Back" onclick={onback} disabled={!canback}><ArrowLeft size={19}/></button>
      <button class="icon-button" aria-label="Forward" title="Forward" onclick={onforward} disabled={!canforward}><ArrowRight size={19}/></button>
      <button class="icon-button" aria-label="Home" title="Home" onclick={onhome}><Home size={17}/></button>
    </div>
    <div><span>Vocabulary block</span><h1>{block.name}</h1></div>
    <div class="header-actions">
      <button class="primary" onclick={onstudy} disabled={!entries.length}><BookOpen size={16}/>Study</button>
    </div>
  </header>
  <div class="toolbar"><Search size={17}/><input bind:value={search} placeholder="Search vocabulary…"/></div>
  {#if entries.length}
    <div class="list">
      {#each entries as entry (entry.blockEntryId)}
        <article>
          <div class="word"><strong>{entry.word}</strong><span>{entry.ipa} · {entry.partOfSpeech}</span></div>
          <p>{entry.viMeaning}</p>
          <div class="mastery"><span style={`width:${Math.min(100,entry.masteryScore*4)}%`}></span></div>
          <small>{entry.totalReviews} reviews</small>
          <button class="icon-button" title="Edit" onclick={() => editing = {...entry}}><Pencil size={15}/></button>
          <button class="icon-button danger-text" title="Remove" onclick={() => remove(entry)}><Trash2 size={15}/></button>
        </article>
      {/each}
    </div>
  {:else}
    <div class="empty">
      <h2>This block has no vocabulary yet.</h2>
      <p>Return to the library and use this block's ⋯ menu to import vocabulary.</p>
    </div>
  {/if}
</section>

{#if editing}
  <Modal title={`Edit ${editing.word}`} onclose={() => editing = null}>
    <form onsubmit={(event) => { event.preventDefault();save(); }}>
      <label>Word<input bind:value={editing.word}/></label>
      <label>IPA<input bind:value={editing.ipa}/></label>
      <label>Part of speech<input bind:value={editing.partOfSpeech}/></label>
      <label>Vietnamese meaning<textarea bind:value={editing.viMeaning}></textarea></label>
      <label>English definition<textarea bind:value={editing.enDefinition}></textarea></label>
      <label>Meaning example (EN)<textarea bind:value={editing.exampleMeaningEn}></textarea></label>
      <label>Meaning example (VI)<textarea bind:value={editing.exampleMeaningVi}></textarea></label>
      <label>Usage example (EN)<textarea bind:value={editing.exampleUsageEn}></textarea></label>
      <label>Usage example (VI)<textarea bind:value={editing.exampleUsageVi}></textarea></label>
      <footer><button class="ghost" type="button" onclick={() => editing = null}>Cancel</button><button class="primary">Save changes</button></footer>
    </form>
  </Modal>
{/if}

<style>
  .manager{max-width:1100px;margin:auto}
  header{display:flex;align-items:center;gap:15px;margin-bottom:28px}
  .navigation-controls{display:flex;align-items:center;padding-right:10px;border-right:1px solid var(--border)}
  .navigation-controls .icon-button{width:32px;height:32px}
  .navigation-controls .icon-button:disabled{transform:none;background:transparent}
  header span{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.13em}
  h1{font-size:24px}
  .header-actions{margin-left:auto;display:flex;gap:9px}
  .toolbar{height:44px;display:flex;align-items:center;gap:10px;padding:0 13px;margin-bottom:14px;background:var(--surface-1);border:1px solid var(--border);border-radius:11px;color:var(--text-muted);box-shadow:0 3px 12px #20334f08}
  .toolbar input{padding:0;border:0;background:none}
  .list{display:grid;gap:7px}
  .list article{display:grid;grid-template-columns:minmax(160px,.8fr) minmax(220px,1.5fr) 100px 70px 34px 34px;gap:14px;align-items:center;padding:13px 14px;background:var(--surface-1);border:1px solid var(--border);border-radius:11px}
  .word{display:grid;gap:3px}
  .word span,small{color:var(--text-muted);font-size:11px}
  .list p{color:var(--text-secondary);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mastery{height:4px;background:#1c2b4112;border-radius:3px}
  .mastery span{display:block;height:100%;background:var(--accent);border-radius:inherit}
  .empty{min-height:350px;display:grid;place-content:center;justify-items:center;text-align:center}
  .empty p{color:var(--text-muted);margin:8px 0 20px}
  form{display:grid;grid-template-columns:1fr 1fr;gap:13px}
  form label{display:grid;gap:6px;font-size:12px;color:var(--text-secondary)}
  form label:nth-child(n+4){grid-column:1/-1}
  form textarea{min-height:70px}
  form footer{grid-column:1/-1;display:flex;justify-content:flex-end;gap:9px;margin-top:6px}
  @media(max-width:950px){.list article{grid-template-columns:1fr 1.4fr 70px 34px 34px}.mastery{display:none}}
</style>
