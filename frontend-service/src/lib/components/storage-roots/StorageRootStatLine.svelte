<script lang="ts">
  import { t } from '$lib/i18n';
  import { timeAgo } from '$lib/utils/format';
  import EntityStatLine from '$lib/components/entity/EntityStatLine.svelte';
  import type { StorageRootPermissionsData } from '$lib/api/storage-root-permissions';

  /** The figures of a storage root on one line, separated by rules instead of cards. */
  export let permissions: StorageRootPermissionsData | null = null;
  export let openAlerts = 0;
  export let lastProbeText = '';
  export let alertsHref = '';
  export let onOpenPermissions: () => void = () => {};

  const ACL_STATE: Record<StorageRootPermissionsData['status'], () => string> = {
    ok: () => t('Compliant'),
    applying: () => t('Being applied'),
    gap: () => t('Gap to review'),
    missing_ace: () => t('ACE missing'),
    never_scanned: () => t('Never read')
  };

  $: summary = permissions?.summary;
  $: nextEnd = (permissions?.people ?? [])
    .filter((p) => p.expires_at)
    .sort((a, b) => String(a.expires_at).localeCompare(String(b.expires_at)))[0];

  const ACL_TONE = { ok: 'success', gap: 'warning', missing_ace: 'danger', never_scanned: 'muted' } as const;
  $: status = permissions?.status ?? 'never_scanned';
  $: aclHint = permissions?.acl_scanned_at
    ? [
        t('{ok}/{total} groups in place', { ok: summary?.groups_ok ?? 0, total: summary?.groups ?? 0 }),
        t('read {ago}', { ago: timeAgo(permissions.acl_scanned_at) }),
        ...(permissions.inheritance?.broken ? [t('inheritance broken')] : [])
      ].join(' · ')
    : t('Read the ACL to see who reaches this folder.');
  $: items = [
    {
      key: 'people',
      label: t('People with access'),
      value: summary ? summary.people : '—',
      big: true,
      note: summary ? t('{read} read · {write} modify', { read: summary.read, write: summary.write }) : '',
      split: summary ? { read: summary.read, write: summary.write } : null,
      onClick: onOpenPermissions
    },
    { key: 'acl', label: t('ACL of the folder'), value: ACL_STATE[status](), tone: ACL_TONE[status], hint: aclHint },
    {
      key: 'ending',
      label: t('Ending within 30 days'),
      value: summary ? t('{count} person(s)', { count: summary.expiring_30d }) : '—',
      hint: nextEnd?.expires_at
        ? t('Next: {name}, in {days} d', { name: nextEnd.name, days: Math.max(0, Math.ceil((Date.parse(nextEnd.expires_at) - Date.now()) / 86400000)) })
        : t('No end date to come')
    },
    {
      key: 'alerts',
      label: t('Alerts'),
      value: openAlerts > 0 ? t('{count} open', { count: openAlerts }) : t('No open alert'),
      tone: openAlerts > 0 ? 'warning' as const : undefined,
      hint: lastProbeText,
      href: alertsHref
    }
  ];
</script>

<EntityStatLine {items} ariaLabel={t('Storage root summary')} />
