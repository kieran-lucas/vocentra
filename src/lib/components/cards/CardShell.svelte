<script lang="ts">
  import { animate } from '../../motion';
  import type { VocabularyEntry } from '../../api/types';
  import CardFront from './CardFront.svelte';
  import CardBack from './CardBack.svelte';
  let { entry,revealed,onreveal,oncounts }=$props<{entry:VocabularyEntry;revealed:boolean;onreveal:()=>void;oncounts:(c:number,e:number)=>void}>();
  let shell:HTMLDivElement;
  $effect(()=>{
    revealed;
    entry.id;
    const animation=animate(shell,[{transform:'translateY(6px)',opacity:.8},{transform:'translateY(0)',opacity:1}]);
    return()=>animation?.cancel();
  });
</script>
<div class="shell" bind:this={shell}>{#if revealed}<CardBack {entry} {oncounts}/>{:else}<CardFront {entry} {onreveal}/>{/if}</div>
<style>.shell{width:min(var(--card-width),100%);height:min(var(--card-height),calc(100vh - 205px));min-height:430px;margin:auto;background:radial-gradient(circle at 90% 5%,#dcecff 0,transparent 30%),linear-gradient(145deg,#ffffff,#f7f9fc);border:1px solid var(--border-strong);border-top:3px solid var(--accent);border-radius:var(--radius-xl);box-shadow:var(--shadow-xl);overflow:hidden;transform-origin:center}</style>
