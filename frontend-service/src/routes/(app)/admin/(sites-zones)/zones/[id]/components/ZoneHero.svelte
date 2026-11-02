<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityActionGroup, { type EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';

  /** Header of a zone, as a card: icon, name, one status pill, its code, directories and servers, actions. */
  export let zone: any;
  export let healthLabel: 'ok' | 'warning' = 'warning';
  export let endpointCount = 0;
  export let directories: string[] = [];
  export let serversLabel = '';
  export let onEdit: (() => void) | null = null;
  export let onDelete: (() => void) | null = null;
  export let onAddEndpoint: (() => void) | null = null;

  // Nothing to report without a server
  $: statusLabel = endpointCount === 0 ? '' : healthLabel === 'ok' ? t('Under control') : t('Needs attention');
  $: actions = [
    { key: 'edit', label: t('Edit'), icon: 'bi-pencil', variant: 'secondary', onClick: () => onEdit?.() },
    ...(onAddEndpoint
      ? [{ key: 'add-endpoint', label: t('Add a server'), icon: 'bi-plus-lg', variant: 'primary' as const, onClick: () => onAddEndpoint?.() }]
      : []),
    { key: 'delete', label: t('Delete zone'), icon: 'bi-trash', variant: 'danger', overflow: true, onClick: () => onDelete?.() }
  ] satisfies EntityActionItem[];
</script>

<header class="zh">
  <span class="zh__icon" aria-hidden="true"><i class="bi bi-geo-alt"></i></span>
  <div class="zh__main">
    <nav class="zh__crumbs" aria-label={t('Location')}><span>{t('Zones')}</span></nav>
    <div class="zh__title">
      <h1>{zone?.name ?? t('Zone')}</h1>
      {#if statusLabel}<span class={`zh__pill is-${healthLabel === 'ok' ? 'success' : 'warning'}`}><span aria-hidden="true"></span>{statusLabel}</span>{/if}
    </div>
    <div class="zh__meta">
      {#if zone?.code}<span class="mono">{zone.code}</span>{/if}
      {#each directories as directory (directory)}<span><i class="bi bi-diagram-3" aria-hidden="true"></i>{directory}</span>{/each}
      {#if serversLabel}<span><i class="bi bi-hdd-network" aria-hidden="true"></i>{serversLabel}</span>{/if}
    </div>
  </div>
  <div class="zh__actions"><EntityActionGroup {actions} ariaLabel={t('Zone actions')} /></div>
</header>

<style>
  .zh { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 16px; align-items: center; padding: 18px 20px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); box-shadow: var(--b2s-shadow-sm); }
  .zh__icon { display: grid; place-items: center; width: 48px; height: 48px; border-radius: 14px; background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 22px; }
  .zh__main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .zh__crumbs { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .zh__title { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .zh__title h1 { margin: 0; font-size: var(--b2s-fs-page-title, 24px); font-weight: 600; letter-spacing: -0.01em; overflow-wrap: anywhere; }
  .zh__pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-xs); font-weight: 500; }
  .zh__pill span { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .zh__pill.is-success { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .zh__pill.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .zh__meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
  .zh__meta span { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-xs); }
  .zh__meta .mono { font-family: var(--b2s-font-mono); }
  .zh__actions { align-self: start; }
</style>
