<script lang="ts">
  import { t } from '$lib/i18n';
  import type { ZoneSummary } from './zone-summary';

  /** The figures of a zone as four tiles: servers reachable, folders to review, pending requests, guardians. */
  export let summary: ZoneSummary;
  export let pendingRequests = 0;
  export let minGuardians = 2;
  export let onOpenServers: () => void = () => {};
  export let onOpenFolders: () => void = () => {};
  export let onOpenRequests: () => void = () => {};
  export let onOpenGuardians: () => void = () => {};

  $: files = summary.files.length;
  $: down = summary.unreachable.length;
  $: roots = summary.roots.length;
  $: review = summary.review.length;
</script>

<section class="zt" aria-label={t('Zone summary')}>
  <button type="button" class="zt__tile" on:click={onOpenServers}>
    <span>{t('Servers reachable')}</span>
    <b class:bad={down > 0}>{files ? `${summary.reachable} / ${files}` : '—'}</b>
    <small>
      {down ? t('{count} unreachable', { count: down }) : files ? t('all answer') : t('No file server yet')}{summary.dfs.length ? ` · ${t('+ {count} DFS namespace(s)', { count: summary.dfs.length })}` : ''}
    </small>
    {#if files}<span class="zt__bar" aria-hidden="true"><i style={`flex:${summary.reachable}`}></i><i class="bad" style={`flex:${down}`}></i><i class="mute" style={`flex:${files - summary.reachable - down}`}></i></span>{/if}
  </button>
  <button type="button" class="zt__tile" on:click={onOpenFolders}>
    <span>{t('Managed folders')}</span>
    <b>{roots}</b>
    <small>{review ? t('{count} to review', { count: review }) : roots ? t('all in order') : t('No managed folder')}</small>
    {#if roots}<span class="zt__bar" aria-hidden="true"><i style={`flex:${roots - review}`}></i><i class="warn" style={`flex:${review}`}></i></span>{/if}
  </button>
  <button type="button" class="zt__tile" on:click={onOpenRequests}>
    <span>{t('Pending requests')}</span>
    <b class:warn={pendingRequests > 0}>{pendingRequests}</b>
    <small>{pendingRequests ? t('to decide by the guardians') : t('nothing to decide')}</small>
  </button>
  <button type="button" class="zt__tile" on:click={onOpenGuardians}>
    <span>{t('Without enough guardians')}</span>
    <b class:warn={summary.noGuardian.length > 0}>{summary.noGuardian.length}</b>
    <small>{t('minimum: {count} guardians per folder', { count: minGuardians })}</small>
  </button>
</section>

<style>
  .zt { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .zt__tile { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); color: inherit; font: inherit; text-align: left; cursor: pointer; transition: box-shadow 0.12s; }
  .zt__tile:hover { box-shadow: 0 6px 18px rgba(14, 18, 24, 0.06); }
  .zt__tile > span:first-child { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .zt__tile b { font-size: 24px; font-weight: 600; line-height: 1.25; }
  .zt__tile b.bad { color: var(--b2s-color-danger-strong); }
  .zt__tile b.warn { color: var(--b2s-color-warning-strong); }
  .zt__tile small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .zt__bar { display: flex; align-self: stretch; width: 100%; gap: 2px; height: 5px; margin-top: 8px; overflow: hidden; border-radius: 99px; }
  .zt__bar i { display: block; min-width: 0; border-radius: 99px; background: var(--b2s-color-success); }
  .zt__bar i.bad { background: var(--b2s-color-danger); }
  .zt__bar i.warn { background: var(--b2s-color-warning); }
  .zt__bar i.mute { background: var(--b2s-color-border); }
</style>
