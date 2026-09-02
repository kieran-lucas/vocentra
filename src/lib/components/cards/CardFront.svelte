<script lang="ts">
  import WordHeader from './WordHeader.svelte';
  import AudioButton from './AudioButton.svelte';
  import type { VocabularyEntry } from '../../api/types';

  let { entry, onreveal }=$props<{entry:VocabularyEntry;onreveal:()=>void}>();
</script>

<div class="front">
  <button class="reveal" onclick={onreveal} aria-label="Reveal answer">
    <WordHeader word={entry.word} ipa={entry.ipa} partOfSpeech={entry.partOfSpeech}/>
    <span class="hint">Press Space or click to reveal</span>
  </button>
  <div class="audio-position"><AudioButton path={entry.audioPath}/></div>
</div>

<style>
  .front{position:relative;width:100%;height:100%}.reveal{width:100%;height:100%;display:grid;place-content:center;gap:85px;background:none;border:0;color:inherit}.audio-position{position:absolute;left:50%;top:calc(50% + 58px);transform:translateX(-50%)}.hint{font-size:11px;text-transform:uppercase;letter-spacing:.14em;color:var(--text-muted)}
</style>
