import { t } from '$lib/i18n';
import type { StatusVariant } from '$lib/utils/status';

/** Readable names of the worker jobs (job_type), translated when read */
const JOB_TYPE_LABELS: Record<string, () => string> = {
  INFRA_HEALTH: () => t('Health check'),
  DIRECTORY_SNAPSHOT: () => t('Directory snapshot'),
  IDENTITY_DISCOVERY: () => t('Directory search'),
  IDENTITY_SEARCH: () => t('Directory search'),
  LDAP_TEST: () => t('Identity source test'),
  SMB_PROBE: () => t('File server test'),
  AD_GROUP_ENSURE: () => t('AD group'),
  AD_ACCESS_GRANT: () => t('AD access'),
  AD_GROUP_MEMBERSHIP: () => t('AD group member'),
  AD_GROUP_MEMBER: () => t('AD group member'),
  AD_GROUP_MEMBERSHIP_REMOVE: () => t('AD group member removal'),
  GROUP_USERS_DISCOVERY: () => t('Group members'),
  ACL_APPLY: () => t('NTFS ACL'),
  SENSITIVITY_SCAN: () => t('Sensitivity scan'),
  FOLDER_SCAN: () => t('Folder measure'),
  FOLDER_LIST: () => t('Folder listing'),
  FOLDER_CREATE: () => t('Folder creation'),
  FOLDER_DELETE: () => t('Folder deletion'),
  FOLDER_INHERITANCE: () => t('Inheritance change'),
  FOLDER_QUOTA_READ: () => t('Quota reading'),
  FOLDER_QUOTA_APPLY: () => t('Quota change'),
  SHARE_CREATE: () => t('Share creation'),
  SHARE_DELETE: () => t('Share deletion'),
  DFS_FOLDER_CREATE: () => t('DFS link creation'),
  DFS_FOLDER_DELETE: () => t('DFS link deletion')
};

/** Some job types cover several actions: the action tells them apart */
const ACTION_LABELS: Record<string, () => string> = {
  test_smb_root_access: () => t('Storage root test'),
  test_smb_ntlm: () => t('File server test'),
  test_ldap: () => t('LDAP connection test'),
  test_ldaps: () => t('LDAPS connection test'),
  fetch_tls_certificate: () => t('TLS certificate reading'),
  resolve_name: () => t('Name resolution'),
  read_dfs_namespaces: () => t('DFS namespaces reading'),
  discover_smb_server: () => t('File server discovery')
};

/** Where a job came from (its context), in words */
export function jobOriginLabel(origin: unknown): string {
  const key = String(origin ?? '').trim().toLowerCase();
  const labels: Record<string, () => string> = {
    retry: () => t('Retried from Observability'),
    policy: () => t('Policy'),
    schedule: () => t('Schedule'),
    scheduler: () => t('Schedule'),
    platform: () => t('Platform'),
    admin: () => t('Administration screen'),
    sensitivity_scan: () => t('Sensitivity scan asked'),
    folder_measure: () => t('Measure asked'),
    first_launch: () => t('First launch')
  };
  return labels[key]?.() ?? key.replace(/_/g, ' ');
}

/** 0.4 s, 12 s, 3 min 05 s, 1 h 02 min */
export function formatSeconds(value: unknown): string {
  if (value == null || value === '') return '—';
  const total = Math.max(0, Math.round(Number(value)));
  if (!Number.isFinite(total)) return '—';
  if (total < 1) return '< 1 s';
  if (total < 60) return `${total} s`;
  if (total < 3600) return `${Math.floor(total / 60)} min ${String(total % 60).padStart(2, '0')} s`;
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return days ? t('{days} d {hours} h', { days, hours }) : `${hours} h ${String(minutes).padStart(2, '0')} min`;
}

export function jobTypeLabel(jobType: unknown, action?: unknown): string {
  const byAction = ACTION_LABELS[String(action ?? '')];
  if (byAction) return byAction();
  const key = String(jobType ?? '').toUpperCase();
  return JOB_TYPE_LABELS[key]?.() ?? (key || '—');
}

export const JOB_TYPES = Object.keys(JOB_TYPE_LABELS);

export function normalizeJobStatus(raw: unknown): string {
  const s = String(raw ?? '').trim().toUpperCase();
  if (!s) return 'UNKNOWN';
  return s === 'CANCELED' ? 'CANCELLED' : s;
}

export function jobStatusLabel(raw: unknown): string {
  const s = normalizeJobStatus(raw);
  return (
    {
      CREATED: t('Queued'),
      QUEUED: t('Queued'),
      RUNNING: t('Running'),
      RETRYING: t('Retrying'),
      SUCCEEDED: t('Succeeded'),
      FAILED: t('Failed'),
      CANCELLED: t('Cancelled')
    } as Record<string, string>
  )[s] ?? s;
}

export function jobStatusVariant(raw: unknown): StatusVariant {
  const s = normalizeJobStatus(raw);
  if (['CREATED', 'QUEUED', 'RUNNING', 'RETRYING'].includes(s)) return 'info';
  if (s === 'SUCCEEDED') return 'success';
  if (s === 'FAILED') return 'error';
  return 'muted';
}

export const isActiveJob = (raw: unknown) => ['CREATED', 'QUEUED', 'RUNNING', 'RETRYING'].includes(normalizeJobStatus(raw));
