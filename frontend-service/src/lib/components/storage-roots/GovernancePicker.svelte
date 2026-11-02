<script lang="ts">
  import { t } from '$lib/i18n';

  type Option = { id: number; label: string; hint?: string };

  export let id: string;
  export let label: string;
  export let placeholder: string;
  export let options: Option[] = [];
  export let selected: number[] = [];

  let query = '';
  const MAX_SHOWN = 8;

  $: chosen = options.filter((option) => selected.includes(option.id));
  $: matches = query.trim()
    ? options
        .filter((option) => !selected.includes(option.id))
        .filter((option) => `${option.label} ${option.hint ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()))
    : [];

  function add(option: Option) {
    selected = [...selected, option.id];
    query = '';
  }
</script>

<div class="picker">
  <label for={id}>{label}</label>
  {#if chosen.length}
    <ul class="chips">
      {#each chosen as option (option.id)}
        <li>
          {option.label}
          <button type="button" aria-label={t('Remove {name}', { name: option.label })} on:click={() => (selected = selected.filter((value) => value !== option.id))}>×</button>
        </li>
      {/each}
    </ul>
  {/if}
  <input {id} class="b2s-input" autocomplete="off" {placeholder} bind:value={query} />
  {#if query.trim()}
    <div class="matches">
      {#each matches.slice(0, MAX_SHOWN) as option (option.id)}
        <button type="button" on:click={() => add(option)}>
          <span>{option.label}</span>
          {#if option.hint}<small>{option.hint}</small>{/if}
        </button>
      {:else}
        <p>{t('No result.')}</p>
      {/each}
    </div>
  {/if}
</div>

<style>
  .picker { display: flex; flex-direction: column; gap: 5px; }
  label { font-size: var(--b2s-text-sm); font-weight: 500; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; margin: 0; padding: 0; list-style: none; }
  .chips li { display: flex; align-items: center; gap: 4px; padding: 1px 4px 1px 9px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-font-micro); }
  .chips button { border: 0; background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
  .matches { display: flex; flex-direction: column; max-height: 170px; overflow: auto; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  .matches button { display: flex; flex-direction: column; padding: 6px 10px; border: 0; border-bottom: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface); text-align: left; cursor: pointer; font-size: var(--b2s-text-sm); }
  .matches button:hover { background: var(--b2s-color-surface-soft); }
  .matches small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); overflow-wrap: anywhere; }
  .matches p { margin: 0; padding: 8px 10px; color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
</style>
