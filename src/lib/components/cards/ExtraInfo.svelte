<script lang="ts">
  type AdditionalItem = { id:string; kind:string; salience:number; text:string|null; note:string|null; attributes?:Record<string,unknown> };
  let { entry } = $props<{entry:any}>();
  const LABELS:Record<string,string> = { pattern:'Pattern', collocation:'Collocation', usage:'Usage', relation:'Related', wordFormation:'Word family', expression:'Expression' };
  const parse=(value:string)=>{try{return JSON.parse(value) as string[]}catch{return[]}};
  // Imported senses carry the Additional v1 envelope; pilot cards carry the
  // legacy list columns. Render whichever the row actually has.
  const additional=$derived((()=>{
    try { const parsed=JSON.parse(entry.extraMetadata||'{}'); return Array.isArray(parsed?.items)?parsed.items as AdditionalItem[]:[] }
    catch { return [] as AdditionalItem[] }
  })());
  const ordered=$derived([...additional].sort((a,b)=>a.salience-b.salience));
  const legacy=$derived([{label:'Collocations',values:parse(entry.collocations)},{label:'Word family',values:parse(entry.wordFamily)},{label:'Synonyms',values:parse(entry.synonyms)},{label:'Antonyms',values:parse(entry.antonyms)}].filter(item=>item.values.length));
  const subtype=(item:AdditionalItem)=>{const attributes=item.attributes??{};const value=attributes.patternType??attributes.relation??attributes.usageType??attributes.relationType??attributes.expressionType;return typeof value==='string'?value:null};
  const visible=$derived(ordered.length>0||legacy.length>0||Boolean(entry.usageNote)||Boolean(entry.register));
</script>

{#if visible}
  <details>
    <summary>More language notes{ordered.length?` (${ordered.length})`:''}</summary>
    <div>
      {#each ordered as item (item.id)}
        <p class="item">
          <b>{LABELS[item.kind] ?? item.kind}</b>
          {#if subtype(item)}<i>{subtype(item)}</i>{/if}
          {#if item.text}<span class="text">{item.text}</span>{/if}
          {#if item.note}<span class="note">{item.note}</span>{/if}
        </p>
      {/each}
      {#if entry.usageNote && !ordered.length}<p><b>Usage</b> {entry.usageNote}</p>{/if}
      {#if entry.register}<p><b>Register</b> {entry.register}</p>{/if}
      {#each legacy as item}<p><b>{item.label}</b> {item.values.join(' · ')}</p>{/each}
    </div>
  </details>
{/if}

<style>
  details{font-size:12px;color:var(--text-secondary)}
  summary{cursor:pointer;color:var(--text-muted)}
  details div{display:grid;gap:7px;margin-top:10px}
  b{color:var(--text-primary);margin-right:8px}
  .item{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px}
  .item i{padding:1px 5px;border:1px solid var(--border);border-radius:4px;color:var(--text-muted);font-size:9px;font-style:normal;text-transform:uppercase;letter-spacing:.08em}
  .item .text{color:var(--text-primary)}
  .item .note{color:var(--text-secondary)}
</style>
