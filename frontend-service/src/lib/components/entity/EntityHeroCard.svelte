<script lang="ts">
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import EntityActionGroup, { type EntityActionItem } from './EntityActionGroup.svelte';

  /**
   * Header of an entity page, as a card: icon, breadcrumb, name, one status pill, small chips
   * (code, directory…), an optional path to copy, and the actions.
   */
  type Tone = 'success' | 'warning' | 'danger' | 'neutral';
  export let icon = 'bi-box';
  export let iconTone: 'green' | 'blue' | 'neutral' = 'neutral';
  export let crumbs: string[] = [];
  export let title = '';
  export let statusLabel = '';
  export let statusTone: Tone = 'neutral';
  export let chips: Array<{ label: string; icon?: string; mono?: boolean }> = [];
  export let path = '';
  export let actions: EntityActionItem[] = [];
  export let actionsAriaLabel = t('Entity actions');

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(path);
      toast.success(t('Path copied.'));
    } catch {
      toast.error(t('The path could not be copied.'));
    }
  }
</script>

<header class="ehc">
  <span class={`ehc__icon is-${iconTone}`} aria-hidden="true"><i class={`bi ${icon}`}></i></span>
  <div class="ehc__main">
    {#if crumbs.length}
      <nav class="ehc__crumbs" aria-label={t('Location')}>
        {#each crumbs as crumb, index}{#if index}<i class="bi bi-chevron-right" aria-hidden="true"></i>{/if}<span>{crumb}</span>{/each}
      </nav>
    {/if}
    <div class="ehc__title">
      <h1>{title}</h1>
      {#if statusLabel}<span class={`ehc__pill is-${statusTone}`}><span aria-hidden="true"></span>{statusLabel}</span>{/if}
    </div>
  </div>
  <div class="ehc__actions"><EntityActionGroup {actions} ariaLabel={actionsAriaLabel} /></div>
  {#if path || chips.length}
    <div class="ehc__meta">
      {#if path}
        <span class="ehc__path">
          <code title={path}>{path}</code>
          <button type="button" on:click={copyPath} aria-label={t('Copy the path')}><i class="bi bi-copy" aria-hidden="true"></i>{t('Copy')}</button>
        </span>
      {/if}
      {#each chips as chip (chip.label)}
        <span class="ehc__chip" class:mono={chip.mono}>{#if chip.icon}<i class={`bi ${chip.icon}`} aria-hidden="true"></i>{/if}{chip.label}</span>
      {/each}
    </div>
  {/if}
</header>

<style>
  .ehc { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; grid-template-areas: "icon main actions" "icon meta meta"; gap: 4px 16px; align-items: center; padding: 18px 20px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); box-shadow: var(--b2s-shadow-sm); }
  .ehc__icon { grid-area: icon; align-self: start; display: grid; place-items: center; width: 48px; height: 48px; border-radius: 14px; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); font-size: 22px; }
  .ehc__icon.is-green { background: var(--b2s-accent-soft); color: var(--b2s-color-success-strong); }
  .ehc__icon.is-blue { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .ehc__main { grid-area: main; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .ehc__crumbs { display: flex; align-items: center; gap: 6px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ehc__crumbs i { font-size: 10px; }
  .ehc__title { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .ehc__title h1 { margin: 0; font-size: var(--b2s-fs-page-title, 24px); font-weight: 600; letter-spacing: -0.01em; overflow-wrap: anywhere; }
  .ehc__pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-xs); font-weight: 500; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .ehc__pill span { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .ehc__pill.is-success { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .ehc__pill.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .ehc__pill.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .ehc__meta { grid-area: meta; display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
  .ehc__chip { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-xs); }
  .ehc__chip.mono { font-family: var(--b2s-font-mono); }
  .ehc__path { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; padding: 2px 4px 2px 9px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); }
  .ehc__path code { min-width: 0; padding: 0; background: none; color: inherit; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .ehc__path button { display: inline-flex; align-items: center; gap: 4px; flex: none; padding: 1px 8px; border: 0; border-radius: 6px; background: var(--b2s-color-surface); font-size: var(--b2s-fs-xs); cursor: pointer; }
  .ehc__actions { grid-area: actions; align-self: start; }
</style>
