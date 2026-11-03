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

<section class="b2s-stat-tiles" aria-label={t('Namespace summary')}>
  <button type="button" class="b2s-stat-tile" on:click={onOpenFolders}>
    <span>{t('DFS folders')}</span>
    <b>{info ? counts.all : '—'}</b>
    <small>{info?.read_at ? t('read {ago}', { ago: timeAgo(info.read_at) }) : t('never read')}</small>
    {#if counts.all}
      <span class="b2s-stat-bar" aria-hidden="true">
        <i style={`flex:${counts.managed}`}></i><i class="todo" style={`flex:${counts.todo}`}></i><i class="bad" style={`flex:${counts.unknown}`}></i><i class="mute" style={`flex:${rest}`}></i>
      </span>
    {/if}
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenFolders}>
    <span>{t('Managed')}</span>
    <b class:is-ok={counts.all > 0 && counts.managed === counts.all}>{counts.managed}</b>
    <small>{t('their targets are governed folders')}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenFolders}>
    <span>{t('To manage')}</span>
    <b class:is-warn={counts.todo > 0}>{counts.todo}</b>
    <small>{counts.todo ? t('one click manages them on every target') : t('nothing left to manage')}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenFolders}>
    <span>{t('Target servers')}</span>
    <b>{counts.servers}</b>
    <small class:is-bad={counts.unknownServers.length > 0}>
      {counts.unknownServers.length ? t('{count} not declared: {names}', { count: counts.unknownServers.length, names: counts.unknownServers.join(', ') }) : t('all declared')}
    </small>
  </button>
</section>

