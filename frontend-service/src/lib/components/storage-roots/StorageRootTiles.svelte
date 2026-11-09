<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatBytes, timeAgo } from '$lib/utils/format';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import { fivesEnabled } from '$lib/utils/features';
  import type { StorageRootPermissionsData } from '$lib/api/storage-root-permissions';

  /**
   * The figures of a storage root as four tiles, none repeating a card of the page: its ACL, its size and how it
   * grows, its quota, then the accesses ending within 30 days (when there are some) or else how much is cold data.
   * People with access and guardians are in the cards « Who reaches it » and « Governance ».
   */
  export let permissions: StorageRootPermissionsData | null = null;
  export let onOpenPermissions: () => void = () => {};
  /** The row of the folder in the list: size, growth, quota, cold data */
  export let row: Record<string, any> | null = null;
  export let onOpenContent: () => void = () => {};

  $: bytes = row?.content_size_bytes ?? row?.estimated_size_bytes ?? null;
  $: quotaLimit = row?.quota_limit_bytes ?? null;
  $: quotaPct = row?.quota_used_percent ?? null;
  $: quotaTone = quotaPct == null ? '' : quotaPct >= 100 ? 'bad' : quotaPct >= Number(row?.quota_warn_percent ?? 85) ? 'warn' : 'ok';
  $: cold = bytes ? Number(row?.cold_1y_bytes ?? 0) / Number(bytes) : null;
  $: expiring = summary?.expiring_30d ?? 0;

  const ACL_STATE: Record<StorageRootPermissionsData['status'], () => string> = {
    ok: () => t('Compliant'),
    applying: () => t('Being applied'),
    gap: () => t('Gap to review'),
    missing_ace: () => t('ACE missing'),
    never_scanned: () => t('Never read')
  };
  const ACL_TONE = { ok: 'ok', applying: 'warn', gap: 'warn', missing_ace: 'bad', never_scanned: 'muted' } as const;

  $: summary = permissions?.summary;
  $: status = permissions?.status ?? 'never_scanned';
  $: total = summary ? summary.read + summary.write : 0;
  $: nextEnd = (permissions?.people ?? [])
    .filter((p) => p.expires_at)
    .sort((a, b) => String(a.expires_at).localeCompare(String(b.expires_at)))[0];
  $: nextDays = nextEnd?.expires_at ? Math.max(0, Math.ceil((Date.parse(nextEnd.expires_at) - Date.now()) / 86400000)) : null;
  $: aclHint = permissions?.acl_scanned_at
    ? [
        t('{ok}/{total} groups in place', { ok: summary?.groups_ok ?? 0, total: summary?.groups ?? 0 }),
        t('read {ago}', { ago: timeAgo(permissions.acl_scanned_at) }),
        ...(permissions.inheritance?.broken ? [t('inheritance broken')] : [])
      ].join(' · ')
    : t('Read the ACL to see who reaches this folder.');
</script>

<section class="b2s-stat-tiles" aria-label={t('Storage root summary')}>
  <button type="button" class="b2s-stat-tile" on:click={onOpenPermissions}>
    <span>{t('ACL of the folder')}</span>
    <b class={`is-${ACL_TONE[status]}`}>{ACL_STATE[status]()}</b>
    <small>{aclHint}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenContent}>
    <span>{t('Size')}</span>
    <b>{#if bytes == null}—{:else}<CountUp value={Number(bytes)} format={(n) => formatBytes(Math.round(n))} />{/if}</b>
    <small>{bytes == null ? t('Not measured yet') : t('{files} file(s) · {folders} sub-folder(s)', { files: Number(row?.content_files ?? 0).toLocaleString('fr-FR'), folders: Number(row?.content_folders ?? 0).toLocaleString('fr-FR') })}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenContent}>
    <span>{t('Quota')}</span>
    <b class={quotaTone ? `is-${quotaTone}` : ''}>{#if quotaLimit == null}{t('None')}{:else if quotaPct == null}{formatBytes(quotaLimit)}{:else}<CountUp value={quotaPct} format={(n) => `${Math.round(n)} %`} />{/if}</b>
    <small>{quotaLimit == null ? t('The folder can grow until the disk is full') : t('of {limit}', { limit: formatBytes(quotaLimit) })}{Number(row?.quota_pending_requests ?? 0) > 0 ? ` · ${t('request waiting')}` : ''}</small>
  </button>
  {#if expiring > 0}
    <button type="button" class="b2s-stat-tile" on:click={onOpenPermissions}>
      <span>{t('Ending within 30 days')}</span>
      <b class="is-warn">{expiring}</b>
      <small>{nextEnd ? t('Next: {name}, in {days} d', { name: nextEnd.name, days: nextDays ?? 0 }) : t('No end date to come')}</small>
    </button>
  {:else if $fivesEnabled}
    <button type="button" class="b2s-stat-tile" on:click={onOpenContent}>
      <span>{t('Cold data')}</span>
      <b class:is-warn={cold != null && cold > 0.5}>{cold == null ? '—' : `${Math.round(cold * 100)} %`}</b>
      <small>{cold == null ? t('Not measured yet') : t('untouched for more than a year')}</small>
    </button>
  {:else}
    <button type="button" class="b2s-stat-tile" on:click={onOpenPermissions}>
      <span>{t('Ending within 30 days')}</span>
      <b>0</b>
      <small>{t('No end date to come')}</small>
    </button>
  {/if}
</section>

