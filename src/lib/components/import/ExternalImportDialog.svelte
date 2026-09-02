<script lang="ts">
  import { onMount } from 'svelte';
  import { FileJson, Mic } from 'lucide-svelte';
  import Modal from '../common/Modal.svelte';
  import { importExternalJson, onImportProgress, speechProfile } from '../../api/external-import';
  import type { ExternalImportEvent, ExternalImportSummary, SpeechProfile } from '../../api/types';

  let { onclose, onimported } = $props<{onclose:()=>void; onimported:(summary:ExternalImportSummary)=>void}>();
  let profile = $state<SpeechProfile|null>(null);
  let fileName = $state(''), json = $state(''), busy = $state(false);
  let errors = $state<string[]>([]), progress = $state<ExternalImportEvent|null>(null), route = $state('');
  let summary = $state<ExternalImportSummary|null>(null);
  const percent = $derived(progress?.total ? Math.round(((progress.current ?? 0) / progress.total) * 100) : 0);

  onMount(() => {
    speechProfile().then((value) => profile = value).catch(() => {});
    const stop = onImportProgress((event) => { if (!busy) return; if (event.stage === 'importer') route = `${event.route} (${event.path})`; else progress = event; });
    return () => { stop.then((unlisten) => unlisten()).catch(() => {}); };
  });

  async function choose(event:Event) {
    const file = (event.target as HTMLInputElement).files?.[0];
    errors = []; summary = null; progress = null;
    if (!file) { fileName = ''; json = ''; return; }
    fileName = file.name;
    json = await file.text();
  }

  async function run() {
    busy = true; errors = []; summary = null; progress = null; route = '';
    try { summary = await importExternalJson(json); onimported(summary); }
    catch (error) { errors = String((error as Error).message).split('\n').filter(Boolean); }
    finally { busy = false; progress = null; }
  }
</script>

<Modal title="Import vocabulary JSON" {onclose}>
  <div class="stack">
    <p>Choose one <code>.json</code> file written to the external vocabulary contract. The file carries the words and the destination block; Lexium generates the pronunciation audio.</p>
    {#if profile}
      <div class="profile"><Mic size={14}/><div><strong>{profile.voice}</strong><span>{profile.sourceFormat} → {profile.finalFormat}</span></div></div>
    {/if}

    <label class="picker">
      <input type="file" accept="application/json,.json" onchange={choose} disabled={busy}/>
      <FileJson size={16}/><span>{fileName || 'Choose a vocabulary JSON file'}</span>
    </label>

    {#if busy}
      <div class="progress" role="status">
        <div class="bar"><i style={`width:${percent}%`}></i></div>
        <small>{progress?.stage === 'audio' ? `Generating audio for “${progress.text}”` : progress?.stage === 'imported' ? `Imported ${progress.entryId}` : progress?.stage === 'validated' ? `Validated ${progress.total} entries → ${progress.destination}` : 'Working…'}{progress?.total ? ` (${progress.current ?? 0}/${progress.total})` : ''}</small>
      </div>
    {/if}

    {#if errors.length}
      <div class="errors">{#each errors as error}<div>{error}</div>{/each}</div>
    {/if}

    {#if summary}
      <div class="summary">
        <h4>{summary.destination}</h4>
        <dl>
          <div><dt>Requested</dt><dd>{summary.requested}</dd></div>
          <div><dt>Imported</dt><dd>{summary.imported}</dd></div>
          <div><dt>Updated</dt><dd>{summary.updated}</dd></div>
          <div><dt>Already current</dt><dd>{summary.alreadyCurrent}</dd></div>
          <div><dt>Audio generated</dt><dd>{summary.audioGenerated}</dd></div>
          <div><dt>Audio reused</dt><dd>{summary.audioReused}</dd></div>
        </dl>
        {#each summary.failed as failure}<p class="fail"><b>{failure.lemma ?? failure.entryId}</b> {failure.reason}</p>{/each}
        {#each summary.needsPronunciationReview as note}<p class="review">{note}</p>{/each}
        {#if summary.warnings.length}<details><summary>{summary.warnings.length} warning(s)</summary>{#each summary.warnings as warning}<p>{warning}</p>{/each}</details>{/if}
        {#if route}<p class="route" data-route={route}>Importer: {route}</p>{/if}
      </div>
    {/if}

    <footer>
      <button class="ghost" onclick={onclose} disabled={busy}>{summary ? 'Close' : 'Cancel'}</button>
      <button class="primary" onclick={run} disabled={!json.trim() || busy}>{busy ? 'Importing…' : 'Import'}</button>
    </footer>
  </div>
</Modal>

<style>
  .stack{display:grid;gap:14px;min-width:min(560px,78vw)}
  .stack>p{font-size:13px;color:var(--text-muted);line-height:1.5}
  .profile{display:flex;align-items:center;gap:10px;padding:9px 12px;border:1px solid var(--border);border-radius:9px;background:var(--surface-3);color:var(--accent-strong)}.profile div{display:grid}.profile strong{font-size:12px}.profile span{font-size:10px;color:var(--text-muted);letter-spacing:.03em}
  .picker{display:flex;align-items:center;gap:10px;padding:16px;border:1px dashed var(--border);border-radius:10px;cursor:pointer;color:var(--text-secondary);font-size:13px}.picker:hover{background:var(--surface-hover)}.picker input{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
  .progress{display:grid;gap:7px}.bar{height:6px;border-radius:3px;background:var(--surface-3);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);transition:width .2s ease}.progress small{font-size:11px;color:var(--text-muted)}
  .errors{max-height:200px;overflow:auto;padding:11px 12px;border-radius:9px;font-size:12px;line-height:1.5;color:#aa3041;background:#d8485b0d;border:1px solid #d8485b33}
  .summary{padding:12px;border-radius:9px;border:1px solid #24845f33;background:#24845f0a}.summary h4{font-size:13px;margin-bottom:9px}.summary dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.summary dl>div{display:grid;gap:2px}.summary dt{font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.1em}.summary dd{font-family:var(--font-display);font-size:16px}
  .route{margin-top:9px;font-size:10px;color:var(--text-muted);word-break:break-all}
  .fail,.review{margin-top:9px;font-size:12px;line-height:1.5}.fail{color:#aa3041}.review{color:#8a6412}
  .summary details{margin-top:9px;font-size:11px;color:var(--text-muted)}.summary details p{margin-top:6px;line-height:1.5}
  footer{display:flex;justify-content:flex-end;gap:10px}
</style>
