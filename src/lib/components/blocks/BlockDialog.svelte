<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import IconPicker from './IconPicker.svelte';
  let { title,initialName='',initialIcon='book-open',onsave,onclose }=$props<{title:string;initialName?:string;initialIcon?:string;onsave:(name:string,icon:string)=>void;onclose:()=>void}>();
  let name=$state(''),icon=$state('book-open'),nameInput:HTMLInputElement;
  onMount(()=>{name=initialName;icon=initialIcon;nameInput.focus()});
</script>

<Modal {title} {onclose}><form onsubmit={(e)=>{e.preventDefault();if(name.trim())onsave(name.trim(),icon)}}><label>Name<input bind:this={nameInput} bind:value={name} maxlength="80" placeholder="e.g. Oxford 5000"/></label><label>Icon<IconPicker value={icon} onchange={(v)=>icon=v}/></label><footer><button type="button" class="ghost" onclick={onclose}>Cancel</button><button type="submit" class="primary" disabled={!name.trim()}>Save block</button></footer></form></Modal>
<style>form{display:grid;gap:20px}label{display:grid;gap:9px;color:var(--text-secondary);font-size:13px}footer{display:flex;justify-content:flex-end;gap:10px}</style>
