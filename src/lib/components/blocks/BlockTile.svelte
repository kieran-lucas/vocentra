<script lang="ts">
  import { MoreHorizontal, Plus, ChevronRight, Upload } from 'lucide-svelte';
  import { icons } from '../../icons/registry';
  import heroArtwork from '../../../assets/lexium-library-hero.jpg';
  import type { BlockSummary } from '../../api/types';

  let { block, onopen, onedit, onadd, onimport, ondelete } = $props<{
    block: BlockSummary;
    onopen: () => void;
    onedit: () => void;
    onadd: () => void;
    onimport: () => void;
    ondelete: () => void;
  }>();
  let menu = $state(false);
  const Icon = $derived(icons[block.iconKey] ?? icons['book-open']);
  const masteryPercent = $derived(Math.min(100,Math.round(block.averageMastery*4)));
  const artPosition = $derived(`${30+(block.id.charCodeAt(0)%5)*12}%`);
</script>

<article class="tile">
  <button class="open" onclick={onopen} aria-label={`Open ${block.name}`}>
    <div class="tile-art" style={`background-image:linear-gradient(120deg,#245a91c9,#5d91c31f),url(${heroArtwork});background-position:center ${artPosition}`}><span class="icon"><Icon size={22}/></span><span class="type">{block.childCount?'COLLECTION':'STUDY DECK'}</span></div>
    <div class="tile-copy"><h3>{block.name}</h3><p>{block.childCount ? `${block.childCount} sub-block${block.childCount===1?'':'s'} · ${block.wordCount} words` : `${block.wordCount} word${block.wordCount===1?'':'s'} ready to study`}</p></div>
    <div class="bottom"><div><span>MASTERY</span><strong>{masteryPercent}%</strong></div><div class="progress"><span style={`width:${masteryPercent}%`}></span></div><ChevronRight size={17}/></div>
  </button>
  <div class="actions">
    <button class="icon-button" aria-label="Block actions" onclick={()=>menu=!menu}><MoreHorizontal size={18}/></button>
    {#if menu}<div class="menu"><button onclick={()=>{menu=false;onedit()}}>Rename & icon</button>{#if block.childCount===0}<button onclick={()=>{menu=false;onimport()}}><Upload size={14}/> Import vocabulary</button>{/if}<button onclick={()=>{menu=false;onadd()}}><Plus size={14}/> Add child</button><button class="danger-text" onclick={()=>{menu=false;ondelete()}}>Delete</button></div>{/if}
  </div>
</article>

<style>
  .tile{position:relative;min-height:248px;background:var(--surface-1);border:1px solid var(--border);border-radius:var(--radius-lg);box-shadow:var(--shadow-sm);overflow:visible;transition:transform var(--motion-fast) var(--ease),border-color var(--motion-fast),box-shadow var(--motion-fast)}
  .tile:hover{transform:translateY(-4px);border-color:var(--border-strong);box-shadow:var(--shadow-lg)}
  .open{width:100%;min-height:246px;padding:0;display:flex;flex-direction:column;text-align:left;background:none;border:0;color:inherit;border-radius:inherit;overflow:hidden}.tile-art{position:relative;height:108px;flex:none;padding:14px;background-size:cover;border-radius:12px 12px 0 0}.tile-art::after{content:"";position:absolute;inset:auto 0 0;height:48px;background:linear-gradient(transparent,#102c4b55)}.icon{position:relative;z-index:1;display:grid;place-items:center;width:39px;height:39px;border:1px solid #ffffff4d;border-radius:8px;color:#fff;background:#0f3c6ccf;box-shadow:0 8px 20px #08254135}.type{position:absolute;z-index:1;left:14px;bottom:11px;color:#fff;font-size:8px;font-weight:700;letter-spacing:.18em}.tile-copy{padding:16px 17px 12px}.tile-copy h3{font-size:19px;letter-spacing:-.015em;margin-bottom:6px}.tile-copy p{color:var(--text-muted);font-size:11px}
  .actions{position:absolute;z-index:3;right:10px;top:10px}.actions>.icon-button{background:#ffffffdf;color:#385069;box-shadow:0 3px 12px #09274422}.actions>.icon-button:hover{background:#fff}
  .menu{position:absolute;right:0;top:40px;width:164px;z-index:5;padding:6px;background:var(--surface-1);border:1px solid var(--border);border-radius:9px;box-shadow:var(--shadow-lg)}
  .menu button{width:100%;display:flex;align-items:center;gap:7px;padding:9px 10px;background:none;border:0;color:var(--text-secondary);font-size:12px;text-align:left;border-radius:7px}.menu button:hover{background:var(--surface-hover);color:var(--text-primary)}
  .bottom{margin-top:auto;padding:0 17px 15px;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;color:var(--text-muted)}.bottom>div:first-child{display:grid}.bottom>div:first-child span{font-size:7px;letter-spacing:.12em}.bottom>div:first-child strong{font-family:var(--font-display);font-size:11px;color:var(--text-secondary)}.progress{height:4px;border-radius:2px;background:#1c2b4112;overflow:hidden}.progress span{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#6ea7e6);border-radius:inherit}
</style>
