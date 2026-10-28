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
  ACL_APPLY: () => t('NTFS ACL')
};

/** Some job types cover several actions: the action tells them apart */
const ACTION_LABELS: Record<string, () => string> = {
  test_smb_root_access: () => t('Storage root test'),
  test_smb_ntlm: () => t('File server test')
};

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
