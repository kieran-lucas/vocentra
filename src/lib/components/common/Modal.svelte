<script lang="ts">
  import { X } from 'lucide-svelte';
  let { title, open=true, onclose, children } = $props<{title:string;open?:boolean;onclose:()=>void;children:any}>();
  function backdrop(event: MouseEvent){if(event.target===event.currentTarget)onclose()}
</script>

{#if open}
  <div class="backdrop" role="presentation" onclick={backdrop}>
    <div class="modal" role="dialog" aria-modal="true" aria-label={title}>
      <header><h2>{title}</h2><button class="icon-button" aria-label="Close" onclick={onclose}><X size={18}/></button></header>
      <div class="body">{@render children()}</div>
    </div>
  </div>
{/if}

<style>.backdrop{position:fixed;inset:0;z-index:50;background:#20314a66;display:grid;place-items:center;padding:24px;animation:fade .15s ease}.modal{width:min(680px,100%);max-height:min(86vh,820px);overflow:auto;background:var(--surface-1);border:1px solid var(--border);border-radius:var(--radius-lg);box-shadow:var(--shadow-xl)}header{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;padding:20px 22px;border-bottom:1px solid var(--border);background:var(--surface-1)}h2{font-size:18px}.body{padding:22px}@keyframes fade{from{opacity:0}}</style>
