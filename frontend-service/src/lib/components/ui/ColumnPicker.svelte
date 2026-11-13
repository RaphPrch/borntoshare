<script lang="ts">
  import { t } from '$lib/i18n';

  
  interface Props {
    /** Which optional columns a table shows: a small menu of checkboxes (the choice is kept by the page). */
    columns: Array<{ key: string; label: string }>;
    hidden?: string[];
    onChange: (hidden: string[]) => void;
  }

  let { columns, hidden = [], onChange }: Props = $props();
  let open = $state(false);
  let root: HTMLElement | null = $state(null);

  function toggle(key: string) {
    onChange(hidden.includes(key) ? hidden.filter((k) => k !== key) : [...hidden, key]);
  }
  function outside(event: MouseEvent) {
    if (open && root && !root.contains(event.target as Node)) open = false;
  }
</script>

<svelte:window onclick={outside} onkeydown={(event) => { if (event.key === 'Escape') open = false; }} />

<div class="cp" bind:this={root}>
  <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" aria-expanded={open} onclick={() => (open = !open)}>
    <i class="bi bi-layout-three-columns" aria-hidden="true"></i>{t('Columns')}{#if hidden.length}<span class="cp__n">{columns.length - hidden.length}/{columns.length}</span>{/if}
  </button>
  {#if open}
    <div class="cp__menu" role="group" aria-label={t('Columns')}>
      {#each columns as column (column.key)}
        <label>
          <input type="checkbox" checked={!hidden.includes(column.key)} onchange={() => toggle(column.key)} />{column.label}
        </label>
      {/each}
      <small>{t('Drag the edge of a column title to widen it; double-click to reset.')}</small>
    </div>
  {/if}
</div>

<style>
  .cp { position: relative; }
  .cp > button { display: inline-flex; align-items: center; gap: 6px; }
  .cp__n { font-size: 11px; color: var(--b2s-color-text-muted); }
  .cp__menu { position: absolute; right: 0; top: calc(100% + 6px); z-index: 40; width: 240px; display: grid; gap: 2px; padding: 8px; border: 1px solid var(--b2s-color-border); border-radius: 12px;
    background: var(--b2s-color-surface); box-shadow: 0 14px 30px rgba(14, 18, 24, 0.14); }
  .cp__menu label { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 8px; font-size: var(--b2s-fs-sm); cursor: pointer; }
  .cp__menu label:hover { background: var(--b2s-color-surface-muted, #f5f7fb); }
  .cp__menu small { padding: 6px 8px 2px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
