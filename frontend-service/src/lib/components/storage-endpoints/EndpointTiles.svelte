<script lang="ts">
  import { t } from '$lib/i18n';
  import type { ZoneSummary } from '$lib/components/zones/zone-summary';

  /**
   * The figures of a file server as four tiles that filter the folder list below (to review, without enough
   * guardians, pending requests); the last one opens the Shares tab. The state of the connection is in the header.
   */
  export let summary: ZoneSummary;
  export let pendingCount = 0;
  export let sharesNotManaged: number | null = null;
  export let activeFilter = 'all';
  export let onFilter: (key: string) => void = () => {};
  export let onOpenShares: () => void = () => {};

  $: roots = summary.roots.length;
  $: review = summary.review.length;
  const toggle = (key: string) => onFilter(activeFilter === key ? 'all' : key);
</script>

<section class="b2s-stat-tiles" aria-label={t('Storage endpoint summary')}>
  <button type="button" class="b2s-stat-tile" class:is-on={activeFilter === 'todo'} aria-pressed={activeFilter === 'todo'} on:click={() => toggle('todo')}>
    <span>{t('To review')}</span>
    <b class:is-warn={review > 0}>{review}</b>
    <small>{t('{count} managed folder(s)', { count: roots })}</small>
    {#if roots}<span class="b2s-stat-bar" aria-hidden="true"><i style={`flex:${roots - review}`}></i><i class="warn" style={`flex:${review}`}></i></span>{/if}
  </button>
  <button type="button" class="b2s-stat-tile" class:is-on={activeFilter === 'guard'} aria-pressed={activeFilter === 'guard'} on:click={() => toggle('guard')}>
    <span>{t('Without enough guardians')}</span>
    <b class:is-warn={summary.noGuardian.length > 0}>{summary.noGuardian.length}</b>
    <small>{summary.noGuardian.length ? t('Only the administrators can approve their requests') : t('all the folders are covered')}</small>
  </button>
  <button type="button" class="b2s-stat-tile" class:is-on={activeFilter === 'pending'} aria-pressed={activeFilter === 'pending'} on:click={() => toggle('pending')}>
    <span>{t('Pending requests')}</span>
    <b class:is-warn={pendingCount > 0}>{pendingCount}</b>
    <small>{pendingCount ? t('waiting for a guardian') : t('nothing waits')}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenShares}>
    <span>{t('Shares not managed')}</span>
    <b>{sharesNotManaged ?? '—'}</b>
    <small>{sharesNotManaged == null ? t('Never searched') : sharesNotManaged ? t('to manage from the Shares tab') : t('every share is managed')}</small>
  </button>
</section>

<style>
  .is-on { border-color: var(--b2s-color-text) !important; box-shadow: inset 0 0 0 1px var(--b2s-color-text); }
</style>
