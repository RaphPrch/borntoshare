<script lang="ts">
  import { t } from '$lib/i18n';
  import { timeAgo } from '$lib/utils/format';
  import type { StorageRootPermissionsData } from '$lib/api/storage-root-permissions';

  /** The figures of a storage root on one line, separated by rules instead of cards. */
  export let permissions: StorageRootPermissionsData | null = null;
  export let openAlerts = 0;
  export let lastProbeText = '';
  export let alertsHref = '';
  export let onOpenPermissions: () => void = () => {};

  const ACL_STATE: Record<StorageRootPermissionsData['status'], () => string> = {
    ok: () => t('Compliant'),
    gap: () => t('Gap to review'),
    missing_ace: () => t('ACE missing'),
    never_scanned: () => t('Never read')
  };

  $: summary = permissions?.summary;
  $: nextEnd = (permissions?.people ?? [])
    .filter((p) => p.expires_at)
    .sort((a, b) => String(a.expires_at).localeCompare(String(b.expires_at)))[0];
</script>

<section class="srs" aria-label={t('Storage root summary')}>
  <button type="button" class="srs__item is-link" on:click={onOpenPermissions}>
    <span class="srs__label">{t('People with access')}</span>
    <span class="srs__value"><strong>{summary ? summary.people : '—'}</strong>
      {#if summary}<small>{t('{read} read · {write} modify', { read: summary.read, write: summary.write })}</small>{/if}
    </span>
    {#if summary?.people}
      <span class="srs__split" aria-hidden="true"><span class="is-read" style={`flex: ${summary.read}`}></span><span class="is-write" style={`flex: ${summary.write}`}></span></span>
    {/if}
  </button>
  <div class="srs__item">
    <span class="srs__label">{t('ACL of the folder')}</span>
    <strong class={`srs__state is-${permissions?.status ?? 'never_scanned'}`}>{ACL_STATE[permissions?.status ?? 'never_scanned']()}</strong>
    <small>
      {#if permissions?.acl_scanned_at}
        {t('{ok}/{total} groups in place', { ok: summary?.groups_ok ?? 0, total: summary?.groups ?? 0 })} · {t('read {ago}', { ago: timeAgo(permissions.acl_scanned_at) })}
        {#if permissions.inheritance?.broken} · {t('inheritance broken')}{/if}
      {:else}
        {t('Read the ACL to see who reaches this folder.')}
      {/if}
    </small>
  </div>
  <div class="srs__item">
    <span class="srs__label">{t('Ending within 30 days')}</span>
    <strong>{summary ? t('{count} person(s)', { count: summary.expiring_30d }) : '—'}</strong>
    <small>{nextEnd?.expires_at ? t('Next: {name}, in {days} d', { name: nextEnd.name, days: Math.max(0, Math.ceil((Date.parse(nextEnd.expires_at) - Date.now()) / 86400000)) }) : t('No end date to come')}</small>
  </div>
  <a class="srs__item is-link" href={alertsHref}>
    <span class="srs__label">{t('Alerts')}</span>
    <strong class:is-warn={openAlerts > 0}>{openAlerts > 0 ? t('{count} open', { count: openAlerts }) : t('No open alert')}</strong>
    <small>{lastProbeText}</small>
  </a>
</section>

<style>
  .srs {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    border-top: 1px solid var(--b2s-color-border-soft);
    border-bottom: 1px solid var(--b2s-color-border-soft);
  }

  .srs__item {
    display: grid;
    align-content: start;
    gap: 6px;
    min-width: 0;
    padding: 14px 18px;
    border: 0;
    border-left: 1px solid var(--b2s-color-border-soft);
    background: none;
    color: var(--b2s-color-text);
    font: inherit;
    text-align: left;
    text-decoration: none;
  }

  .srs__item:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .srs__item.is-link {
    cursor: pointer;
  }

  .srs__item.is-link:hover strong {
    color: var(--b2s-color-info-strong);
  }

  .srs__label,
  .srs__item small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .srs__item strong {
    font-size: var(--b2s-fs-lg);
    font-weight: 600;
  }

  .srs__value {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }

  .srs__value strong {
    font-size: var(--b2s-fs-2xl);
    font-weight: 700;
  }

  .srs__value small {
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
  }

  .srs__split {
    display: flex;
    gap: 2px;
    height: 4px;
    max-width: 220px;
    overflow: hidden;
    border-radius: var(--b2s-radius-pill);
  }

  .srs__split .is-read { background: var(--b2s-color-info); }
  .srs__split .is-write { background: var(--b2s-color-warning); }

  .srs__state.is-ok { color: var(--b2s-color-success-strong); }
  .srs__state.is-gap { color: var(--b2s-color-warning-strong); }
  .srs__state.is-missing_ace { color: var(--b2s-color-danger-strong); }
  .srs__state.is-never_scanned { color: var(--b2s-color-text-muted); }
  .is-warn { color: var(--b2s-color-warning-strong); }

  @media (max-width: 1100px) {
    .srs {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .srs__item:nth-child(3) {
      padding-left: 0;
      border-left: 0;
    }
  }
</style>
