<script lang="ts">
  import { Volume2, LoaderCircle } from 'lucide-svelte';
  import { playEntryAudio } from '../../api/audio';
  let { path, onerror }=$props<{path:string|null;onerror?:(message:string)=>void}>();
  let busy=$state(false);
  async function play(event:MouseEvent){
    event.stopPropagation();
    if(!path||busy)return;
    busy=true;
    try{await playEntryAudio(path)}catch(error){onerror?.((error as Error).message)}finally{busy=false}
  }
</script>
<button class="audio" class:busy disabled={!path||busy} onclick={play} aria-label={path?'Play pronunciation':'Pronunciation unavailable'} title={path?'Play pronunciation':'Pronunciation unavailable'}>
  {#if busy}<LoaderCircle size={17}/>{:else}<Volume2 size={17}/>{/if}
</button>
<style>
  .audio{display:inline-grid;place-items:center;width:34px;height:34px;border:1px solid var(--border);border-radius:8px;background:var(--surface-1);color:var(--accent);transition:transform var(--motion-fast),background var(--motion-fast),border-color var(--motion-fast)}
  .audio:hover:not(:disabled){transform:translateY(-1px);background:var(--accent-soft);border-color:var(--accent)}.audio:disabled{opacity:.42;cursor:not-allowed}.busy :global(svg){animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
