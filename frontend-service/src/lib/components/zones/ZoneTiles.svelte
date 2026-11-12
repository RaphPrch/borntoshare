<script lang="ts">
  import { t } from '$lib/i18n';
  import type { ZoneSummary } from './zone-summary';

  /** The figures of a zone as four tiles: servers reachable, folders to review, pending requests, guardians. */
  export let summary: ZoneSummary;
  export let pendingRequests = 0;
  export let onOpenServers: () => void = () => {};
  export let onOpenFolders: () => void = () => {};
  export let onOpenRequests: () => void = () => {};
  export let onOpenGuardians: () => void = () => {};

  $: files = summary.files.length;
  $: down = summary.unreachable.length;
  $: roots = summary.roots.length;
  $: review = summary.review.length;
</script>

<section class="b2s-stat-tiles" aria-label={t('Zone summary')}>
  <button type="button" class="b2s-stat-tile" on:click={onOpenServers}>
    <span>{t('Servers reachable')}</span>
    <b class:is-bad={down > 0}>{files ? `${summary.reachable} / ${files}` : '—'}</b>
    <small>
      {down ? t('{count} unreachable', { count: down }) : files ? t('all answer') : t('No file server yet')}{summary.dfs.length ? ` · ${t('+ {count} DFS namespace(s)', { count: summary.dfs.length })}` : ''}
    </small>
    {#if files}<span class="b2s-stat-bar" aria-hidden="true"><i style={`flex:${summary.reachable}`}></i><i class="bad" style={`flex:${down}`}></i><i class="mute" style={`flex:${files - summary.reachable - down}`}></i></span>{/if}
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenFolders}>
    <span>{t('Managed folders')}</span>
    <b>{roots}</b>
    <small>{review ? t('{count} to review', { count: review }) : roots ? t('all in order') : t('No managed folder')}</small>
    {#if roots}<span class="b2s-stat-bar" aria-hidden="true"><i style={`flex:${roots - review}`}></i><i class="warn" style={`flex:${review}`}></i></span>{/if}
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenRequests}>
    <span>{t('Pending requests')}</span>
    <b class:is-warn={pendingRequests > 0}>{pendingRequests}</b>
    <small>{pendingRequests ? t('to decide by the guardians') : t('nothing to decide')}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenGuardians}>
    <span>{t('Without guardian')}</span>
    <b class:is-warn={summary.noGuardian.length > 0}>{summary.noGuardian.length}</b>
    <small>{t('the administrators decide on their requests')}</small>
  </button>
</section>

