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

<section class="tiles" aria-label={t('Storage root summary')}>
  <button type="button" class="tile" on:click={onOpenPermissions}>
    <span>{t('People with access')}</span>
    <b>{summary ? summary.people : '—'}</b>
    <small>{summary ? t('{read} read · {write} modify', { read: summary.read, write: summary.write }) : t('Not read yet')}</small>
    {#if total}
      <span class="tile__split" aria-hidden="true"><i class="read" style={`flex:${summary?.read ?? 0}`}></i><i class="write" style={`flex:${summary?.write ?? 0}`}></i></span>
    {/if}
  </button>
  <button type="button" class="tile" on:click={onOpenPermissions}>
    <span>{t('ACL of the folder')}</span>
    <b class={`is-${ACL_TONE[status]}`}>{ACL_STATE[status]()}</b>
    <small>{aclHint}</small>
  </button>
  <button type="button" class="tile" on:click={onOpenPermissions}>
    <span>{t('Ending within 30 days')}</span>
    <b class:is-warn={Boolean(summary?.expiring_30d)}>{summary ? summary.expiring_30d : '—'}</b>
    <small>{nextEnd ? t('Next: {name}, in {days} d', { name: nextEnd.name, days: nextDays ?? 0 }) : t('No end date to come')}</small>
  </button>
  <button type="button" class="tile" on:click={onOpenGuardians}>
    <span>{t('Guardians')}</span>
    <b class:is-warn={guardiansMissing}>{guardianCount}</b>
    <small>{guardiansMissing ? t('Too few: only the administrators can approve') : t('They approve the requests')}</small>
  </button>
</section>

<style>
  .tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .tile { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); color: inherit; font: inherit; text-align: left; cursor: pointer; transition: box-shadow 0.12s, border-color 0.12s; }
  .tile:hover { border-color: var(--b2s-color-border-mid, var(--b2s-color-border)); box-shadow: 0 6px 18px rgba(14, 18, 24, 0.06); }
  .tile > span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .tile b { font-size: 24px; font-weight: 600; line-height: 1.25; }
  .tile b.is-ok { color: var(--b2s-color-success-strong); }
  .tile b.is-warn { color: var(--b2s-color-warning-strong); }
  .tile b.is-bad { color: var(--b2s-color-danger-strong); }
  .tile b.is-muted { color: var(--b2s-color-text-muted); }
  .tile small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .tile__split { display: flex; align-self: stretch; width: 100%; gap: 2px; height: 6px; margin-top: 8px; }
  .tile__split i { display: block; min-width: 0; border-radius: 3px; }
  .tile__split i.read { background: var(--b2s-color-info); }
  .tile__split i.write { background: var(--b2s-color-warning); }
</style>
