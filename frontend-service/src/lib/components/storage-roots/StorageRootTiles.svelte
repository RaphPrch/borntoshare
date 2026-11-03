<script lang="ts">
  import { t } from '$lib/i18n';
  import { timeAgo } from '$lib/utils/format';
  import type { StorageRootPermissionsData } from '$lib/api/storage-root-permissions';

  /** The figures of a storage root as four tiles: who reaches it, its ACL, the next end dates, its guardians. */
  export let permissions: StorageRootPermissionsData | null = null;
  export let guardianCount = 0;
  export let guardiansMissing = false;
  export let onOpenPermissions: () => void = () => {};
  export let onOpenGuardians: () => void = () => {};

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
    <span>{t('People with access')}</span>
    <b>{summary ? summary.people : '—'}</b>
    <small>{summary ? t('{read} read · {write} modify', { read: summary.read, write: summary.write }) : t('Not read yet')}</small>
    {#if total}
      <span class="b2s-stat-bar" aria-hidden="true"><i class="read" style={`flex:${summary?.read ?? 0}`}></i><i class="write" style={`flex:${summary?.write ?? 0}`}></i></span>
    {/if}
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenPermissions}>
    <span>{t('ACL of the folder')}</span>
    <b class={`is-${ACL_TONE[status]}`}>{ACL_STATE[status]()}</b>
    <small>{aclHint}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenPermissions}>
    <span>{t('Ending within 30 days')}</span>
    <b class:is-warn={Boolean(summary?.expiring_30d)}>{summary ? summary.expiring_30d : '—'}</b>
    <small>{nextEnd ? t('Next: {name}, in {days} d', { name: nextEnd.name, days: nextDays ?? 0 }) : t('No end date to come')}</small>
  </button>
  <button type="button" class="b2s-stat-tile" on:click={onOpenGuardians}>
    <span>{t('Guardians')}</span>
    <b class:is-warn={guardiansMissing}>{guardianCount}</b>
    <small>{guardiansMissing ? t('Too few: only the administrators can approve') : t('They approve the requests')}</small>
  </button>
</section>

