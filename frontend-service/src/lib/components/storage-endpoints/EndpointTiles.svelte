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

<section class="et" aria-label={t('Storage endpoint summary')}>
  <button type="button" class="et__tile" on:click={onOpenConnection}>
    <span>{t('Connection')}</span>
    <b class={`is-${HEALTH[health].tone}`}>{HEALTH[health].label()}</b>
    <small>{lastTest ? t('Last test {when}', { when: lastTest }) : t('Never tested')}</small>
  </button>
  <button type="button" class="et__tile" on:click={onOpenFolders}>
    <span>{t('Managed folders')}</span>
    <b>{roots}</b>
    <small>{review ? t('{count} to review', { count: review }) : roots ? t('all in order') : t('No managed folder')}</small>
    {#if roots}<span class="et__bar" aria-hidden="true"><i style={`flex:${roots - review}`}></i><i class:bad={health === 'unhealthy'} class="warn" style={`flex:${review}`}></i></span>{/if}
  </button>
  <button type="button" class="et__tile" on:click={onOpenGuardians}>
    <span>{t('Without enough guardians')}</span>
    <b class:is-warn={summary.noGuardian.length > 0}>{summary.noGuardian.length}</b>
    <small>{summary.noGuardian.length ? t('Only the administrators can approve their requests') : t('all the folders are covered')}</small>
  </button>
  <button type="button" class="et__tile" on:click={onOpenShares}>
    <span>{t('Shares not managed')}</span>
    <b>{sharesNotManaged ?? '—'}</b>
    <small>{sharesNotManaged == null ? t('Never searched') : sharesNotManaged ? t('to manage from the Shares tab') : t('every share is managed')}</small>
  </button>
</section>

<style>
  .et { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .et__tile { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); color: inherit; font: inherit; text-align: left; cursor: pointer; transition: box-shadow 0.12s; }
  .et__tile:hover { box-shadow: 0 6px 18px rgba(14, 18, 24, 0.06); }
  .et__tile > span:first-child { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .et__tile b { font-size: 24px; font-weight: 600; line-height: 1.25; }
  .et__tile b.is-ok { color: var(--b2s-color-success-strong); }
  .et__tile b.is-warn { color: var(--b2s-color-warning-strong); }
  .et__tile b.is-bad { color: var(--b2s-color-danger-strong); }
  .et__tile b.is-mute { color: var(--b2s-color-text-muted); }
  .et__tile small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .et__bar { display: flex; align-self: stretch; width: 100%; gap: 2px; height: 5px; margin-top: 8px; overflow: hidden; border-radius: 99px; }
  .et__bar i { display: block; min-width: 0; border-radius: 99px; background: var(--b2s-color-success); }
  .et__bar i.warn { background: var(--b2s-color-warning); }
  .et__bar i.bad { background: var(--b2s-color-danger); }
</style>
