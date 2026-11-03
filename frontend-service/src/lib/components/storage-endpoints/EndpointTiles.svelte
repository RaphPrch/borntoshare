<script lang="ts">
  import { t } from '$lib/i18n';
  import type { ZoneSummary } from '$lib/components/zones/zone-summary';

  /** The figures of a file server as four tiles: connection, folders to review, guardians, shares not managed. */
  export let summary: ZoneSummary;
  export let health: 'healthy' | 'degraded' | 'unhealthy' | 'unknown' = 'unknown';
  export let lastTest = '';
  export let sharesNotManaged: number | null = null;
  export let onOpenConnection: () => void = () => {};
  export let onOpenFolders: () => void = () => {};
  export let onOpenGuardians: () => void = () => {};
  export let onOpenShares: () => void = () => {};

  const HEALTH = {
    healthy: { label: () => t('Reachable'), tone: 'ok' },
    degraded: { label: () => t('To review'), tone: 'warn' },
    unhealthy: { label: () => t('Unreachable'), tone: 'bad' },
    unknown: { label: () => t('Not tested'), tone: 'mute' }
  } as const;

  $: roots = summary.roots.length;
  $: review = summary.review.length;
</script>

<section class="b2s-stat-tiles" aria-label={t('Storage endpoint summary')}>
  <button type="button" class="b2s-stat-tile" on:click={onOpenConnection}>
    <span>{t('Connection')}</span>
    <b class={`is-${HEALTH[health].tone}`}>{HEALTH[health].label()}</b>
    <small>{lastTest ? t('Last test {when}', { when: lastTest }) : t('Never tested')}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenFolders}>
    <span>{t('Managed folders')}</span>
    <b>{roots}</b>
    <small>{review ? t('{count} to review', { count: review }) : roots ? t('all in order') : t('No managed folder')}</small>
    {#if roots}<span class="b2s-stat-bar" aria-hidden="true"><i style={`flex:${roots - review}`}></i><i class:bad={health === 'unhealthy'} class="warn" style={`flex:${review}`}></i></span>{/if}
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenGuardians}>
    <span>{t('Without enough guardians')}</span>
    <b class:is-warn={summary.noGuardian.length > 0}>{summary.noGuardian.length}</b>
    <small>{summary.noGuardian.length ? t('Only the administrators can approve their requests') : t('all the folders are covered')}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenShares}>
    <span>{t('Shares not managed')}</span>
    <b>{sharesNotManaged ?? '—'}</b>
    <small>{sharesNotManaged == null ? t('Never searched') : sharesNotManaged ? t('to manage from the Shares tab') : t('every share is managed')}</small>
  </button>
</section>

