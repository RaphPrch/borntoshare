<script lang="ts">
  import { t } from '$lib/i18n';
  import { timeAgo } from '$lib/utils/format';
  import type { DfsCounts, DfsInfo } from './dfs-namespace';

  /** The figures of a DFS namespace as four tiles: its DFS folders, managed, to manage, target servers. */
  export let info: DfsInfo | null = null;
  export let counts: DfsCounts;
  export let onOpenFolders: () => void = () => {};

  $: rest = Math.max(0, counts.all - counts.managed - counts.todo - counts.unknown);
</script>

<section class="dt" aria-label={t('Namespace summary')}>
  <button type="button" class="dt__tile" on:click={onOpenFolders}>
    <span>{t('DFS folders')}</span>
    <b>{info ? counts.all : '—'}</b>
    <small>{info?.read_at ? t('read {ago}', { ago: timeAgo(info.read_at) }) : t('never read')}</small>
    {#if counts.all}
      <span class="dt__bar" aria-hidden="true">
        <i style={`flex:${counts.managed}`}></i><i class="todo" style={`flex:${counts.todo}`}></i><i class="bad" style={`flex:${counts.unknown}`}></i><i class="mute" style={`flex:${rest}`}></i>
      </span>
    {/if}
  </button>
  <button type="button" class="dt__tile" on:click={onOpenFolders}>
    <span>{t('Managed')}</span>
    <b class:is-ok={counts.all > 0 && counts.managed === counts.all}>{counts.managed}</b>
    <small>{t('their targets are governed folders')}</small>
  </button>
  <button type="button" class="dt__tile" on:click={onOpenFolders}>
    <span>{t('To manage')}</span>
    <b class:is-warn={counts.todo > 0}>{counts.todo}</b>
    <small>{counts.todo ? t('one click manages them on every target') : t('nothing left to manage')}</small>
  </button>
  <button type="button" class="dt__tile" on:click={onOpenFolders}>
    <span>{t('Target servers')}</span>
    <b>{counts.servers}</b>
    <small class:bad={counts.unknownServers.length > 0}>
      {counts.unknownServers.length ? t('{count} not declared: {names}', { count: counts.unknownServers.length, names: counts.unknownServers.join(', ') }) : t('all declared')}
    </small>
  </button>
</section>

<style>
  .dt { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .dt__tile { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); color: inherit; font: inherit; text-align: left; cursor: pointer; transition: box-shadow 0.12s; }
  .dt__tile:hover { box-shadow: 0 6px 18px rgba(14, 18, 24, 0.06); }
  .dt__tile > span:first-child { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .dt__tile b { font-size: 24px; font-weight: 600; line-height: 1.25; }
  .dt__tile b.is-ok { color: var(--b2s-color-success-strong); }
  .dt__tile b.is-warn { color: var(--b2s-color-warning-strong); }
  .dt__tile small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .dt__tile small.bad { color: var(--b2s-color-danger-strong); }
  .dt__bar { display: flex; align-self: stretch; width: 100%; gap: 2px; height: 5px; margin-top: 8px; overflow: hidden; border-radius: 99px; }
  .dt__bar i { display: block; min-width: 0; border-radius: 99px; background: var(--b2s-color-success); }
  .dt__bar i.todo { background: var(--b2s-color-warning); }
  .dt__bar i.bad { background: var(--b2s-color-danger); }
  .dt__bar i.mute { background: var(--b2s-color-border); }
</style>
