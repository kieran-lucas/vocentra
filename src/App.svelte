<script lang="ts">
  import { onMount } from 'svelte';
  import gsap from 'gsap';
  import { ChevronRight, Home, Plus, WifiOff, Layers3, BookOpenCheck, Gauge } from 'lucide-svelte';
  import heroArtwork from './assets/lexium-library-hero.jpg';
  import type { BlockSummary } from './lib/api/types';
  import { createBlock, deleteBlock, listBlocks, updateBlock } from './lib/api/blocks';
  import BlockGrid from './lib/components/blocks/BlockGrid.svelte';
  import BlockDialog from './lib/components/blocks/BlockDialog.svelte';
  import VocabularyManager from './lib/components/manage/VocabularyManager.svelte';
  import StudyScreen from './lib/components/study/StudyScreen.svelte';
  import Toast from './lib/components/common/Toast.svelte';

  let blocks = $state<BlockSummary[]>([]);
  let path = $state<BlockSummary[]>([]);
  let mode = $state<'grid'|'manage'|'study'>('grid');
  let active = $state<BlockSummary|null>(null);
  let dialog = $state<{kind:'create'|'edit';parent:string|null;block?:BlockSummary}|null>(null);
  let loading = $state(true);
  let toast = $state<{message:string;kind:'info'|'error'|'success'}|null>(null);
  let view = $state<HTMLElement>();
  const totalWords = $derived(blocks.reduce((total,block)=>total+block.wordCount,0));
  const averageMastery = $derived(blocks.length?Math.round(blocks.reduce((total,block)=>total+block.averageMastery,0)/blocks.length):0);

  function currentParent() { return path.at(-1)?.id ?? null; }
  function notify(message:string,kind:'info'|'error'|'success'='info') {
    toast={message,kind};
    setTimeout(()=>{if(toast?.message===message)toast=null},3200);
  }
  async function load(parent:string|null=currentParent(),direction:1|-1=1) {
    loading=true;
    try {
      const next=await listBlocks(parent);
      if(view)await gsap.to(view,{x:-18*direction,opacity:0,duration:.12,ease:'power1.in'});
      blocks=next;
      requestAnimationFrame(()=>view&&gsap.fromTo(view,{x:22*direction,opacity:0},{x:0,opacity:1,duration:.25,ease:'power3.out'}));
    } catch(error) { notify((error as Error).message,'error'); }
    finally { loading=false; }
  }
  async function open(block:BlockSummary) {
    if(block.childCount){path=[...path,block];await load(block.id,1)}
    else{active=block;mode='manage'}
  }
  async function crumb(index:number) {
    if(index<0){path=[];await load(null,-1)}
    else{path=path.slice(0,index+1);await load(path.at(-1)!.id,-1)}
  }
  async function save(name:string,icon:string) {
    if(!dialog)return;
    try {
      if(dialog.kind==='create')await createBlock(dialog.parent,name,icon);
      else await updateBlock(dialog.block!.id,name,icon);
      await load();dialog=null;notify('Block saved','success');
    } catch(error) { notify((error as Error).message,'error'); }
  }
  async function remove(block:BlockSummary) {
    if(!confirm(`Delete “${block.name}” and everything inside it?`))return;
    try{await deleteBlock(block.id);await load();notify('Block deleted','success')}
    catch(error){notify((error as Error).message,'error')}
  }
  onMount(()=>load(null));
</script>

{#if mode==='study'&&active}
  <StudyScreen block={active} onexit={()=>mode='manage'} onerror={(message)=>notify(message,'error')}/>
{:else if mode==='manage'&&active}
  <main class="page"><VocabularyManager block={active} onback={()=>{mode='grid';active=null;load()}} onstudy={()=>mode='study'} onchange={()=>load()} onerror={(message)=>notify(message,'error')}/></main>
{:else}
  <div class="shell">
    <header class="app-header">
      <div class="brand"><span>lx</span><div><strong>LEXIUM</strong><small>VOCABULARY DESKTOP</small></div></div>
      <nav aria-label="Breadcrumb"><button onclick={()=>crumb(-1)} aria-label="Home"><Home size={15}/></button>{#each path as item,index}<ChevronRight size={13}/><button onclick={()=>crumb(index)}>{item.name}</button>{/each}</nav>
      <div class="offline"><WifiOff size={13}/><span>Offline</span></div>
      <button class="primary" onclick={()=>dialog={kind:'create',parent:currentParent()}}><Plus size={16}/>New block</button>
    </header>
    <main class="content">
      {#if path.length}
        <div class="heading"><span>Collection</span><h1>{path.at(-1)?.name}</h1><p>Choose a block or create another level.</p></div>
      {:else}
        <section class="hero" style={`--hero-art:url(${heroArtwork})`}>
          <div class="hero-copy"><span class="eyebrow">LEXIUM LIBRARY</span><h1>Words worth<br/>remembering.</h1><p>Build focused collections, practise with intent, and let weak vocabulary rise naturally to the top.</p></div>
          <div class="metrics" aria-label="Library overview">
            <div><span class="metric-icon"><Layers3 size={17}/></span><p><strong>{blocks.length}</strong><small>Collections</small></p></div>
            <div><span class="metric-icon"><BookOpenCheck size={17}/></span><p><strong>{totalWords}</strong><small>Words ready</small></p></div>
            <div><span class="metric-icon"><Gauge size={17}/></span><p><strong>{averageMastery}</strong><small>Avg. mastery</small></p></div>
          </div>
        </section>
      {/if}
      <div class="section-title"><div><span>{path.length?'SUB-COLLECTIONS':'YOUR LIBRARY'}</span><h2>{path.length?path.at(-1)?.name:'Browse collections'}</h2></div><small>{blocks.length} available</small></div>
      <section bind:this={view}>{#if loading&&!blocks.length}<div class="loading">Loading library…</div>{:else}<BlockGrid {blocks} onopen={open} oncreate={()=>dialog={kind:'create',parent:currentParent()}} onedit={(block)=>dialog={kind:'edit',parent:block.parentId,block}} onadd={(block)=>dialog={kind:'create',parent:block.id}} ondelete={remove}/>{/if}</section>
    </main>
  </div>
{/if}

{#if dialog}<BlockDialog title={dialog.kind==='create'?'Create block':'Edit block'} initialName={dialog.block?.name} initialIcon={dialog.block?.iconKey} onsave={save} onclose={()=>dialog=null}/>{/if}
{#if toast}<Toast message={toast.message} kind={toast.kind}/>{/if}

<style>
  .shell{height:100%;display:grid;grid-template-rows:70px 1fr;background:linear-gradient(180deg,#f5f7fa,var(--surface-0))}
  .app-header{display:flex;align-items:center;padding:0 30px;border-bottom:1px solid var(--border);background:#fffffff5;box-shadow:0 1px 12px #263b580d}.brand{display:flex;align-items:center;gap:11px;margin-right:40px}.brand>span{display:grid;place-items:center;width:34px;height:34px;background:linear-gradient(145deg,#4389e2,var(--accent-strong));color:#ffffff;border-radius:7px;box-shadow:0 7px 18px #2f73ce2b;font-family:var(--font-display);font-weight:800;letter-spacing:-.08em}.brand>div{display:grid;gap:1px}.brand strong{font-family:var(--font-display);font-size:14px;letter-spacing:.08em}.brand small{font-size:8px;color:var(--text-muted);letter-spacing:.14em}
  nav{min-width:0;display:flex;align-items:center;gap:5px;color:var(--text-muted)}nav button{max-width:180px;padding:7px 8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;background:none;border:0;color:inherit;border-radius:6px;font-size:12px}nav button:hover{color:var(--text-primary);background:var(--surface-hover)}.offline{margin-left:auto;margin-right:16px;display:flex;align-items:center;gap:6px;padding:6px 9px;border:1px solid var(--border);border-radius:5px;color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.09em}.app-header>.primary{min-height:36px}
  .content,.page{height:100%;overflow:auto;padding:clamp(24px,3.2vw,42px)}.content{max-width:1420px;width:100%;margin:auto}.heading{margin-bottom:28px}.heading span,.section-title span{font-size:9px;color:var(--accent);text-transform:uppercase;letter-spacing:.18em;font-weight:700}.heading h1{margin:7px 0;font-size:clamp(29px,4vw,42px);letter-spacing:-.025em}.heading p{color:var(--text-muted)}
  .hero{position:relative;isolation:isolate;min-height:278px;margin-bottom:31px;display:flex;align-items:flex-end;padding:34px 38px;overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-xl);background:#dce6f0;box-shadow:var(--shadow-lg)}.hero::before{content:"";position:absolute;inset:0;z-index:-2;background-image:var(--hero-art);background-size:cover;background-position:center 66%}.hero::after{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(90deg,#f8fbff 0%,#f8fbfff3 31%,#f8fbffba 51%,#f8fbff12 74%)}.hero-copy{max-width:520px}.eyebrow{font-size:9px;color:var(--accent-strong);font-weight:750;letter-spacing:.2em}.hero h1{margin:11px 0 12px;font-size:clamp(38px,5vw,58px);line-height:.98;letter-spacing:-.035em}.hero-copy>p{max-width:455px;color:var(--text-secondary);font-size:13px;line-height:1.6}.metrics{position:absolute;right:22px;bottom:20px;display:flex;padding:7px;background:#ffffffec;border:1px solid var(--border);border-radius:10px;box-shadow:var(--shadow-lg)}.metrics>div{min-width:122px;display:flex;align-items:center;gap:9px;padding:8px 12px;border-right:1px solid var(--border)}.metrics>div:last-child{border:0}.metric-icon{display:grid;place-items:center;width:30px;height:30px;border-radius:7px;color:var(--accent);background:var(--accent-soft)}.metrics p{display:grid}.metrics strong{font-family:var(--font-display);font-size:17px}.metrics small{font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em}
  .section-title{display:flex;align-items:flex-end;justify-content:space-between;margin:0 2px 14px}.section-title>div{display:grid;gap:4px}.section-title h2{font-size:18px;letter-spacing:-.01em}.section-title>small{color:var(--text-muted);font-size:11px}.loading{min-height:300px;display:grid;place-items:center;color:var(--text-muted)}
  @media(max-width:1050px){.metrics{display:none}.hero::after{background:linear-gradient(90deg,#f8fbff 0%,#f8fbffee 45%,#f8fbff44 80%)}}
</style>
