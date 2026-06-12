export type StatusVariant = 'success' | 'warning' | 'info' | 'error' | 'disabled' | 'muted';

export const STATUS_VARIANTS = {
  active: 'success',
  enabled: 'success',
  connected: 'success',
  healthy: 'success',
  synced: 'success',
  success: 'success',
  succeeded: 'success',
  approved: 'success',
  enforced: 'success',
  online: 'success',
  imported: 'success',

  pending: 'warning',
  stale: 'warning',
  warning: 'warning',
  queued: 'warning',
  retrying: 'warning',

  running: 'info',
  probing: 'info',
  processing: 'info',
  in_progress: 'info',

  error: 'error',
  failed: 'error',
  rejected: 'error',
  offline: 'error',
  disconnected: 'error',
  timeout: 'error',
  canceled: 'error',
  cancelled: 'error',

  disabled: 'disabled',
  inactive: 'disabled',
  revoked: 'disabled',

  draft: 'muted',
  unknown: 'muted',
  neutral: 'muted'
} as const satisfies Record<string, StatusVariant>;

export const normalizeStatusKey = (status?: string | null): string =>
  String(status ?? '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');

export const resolveStatusVariant = (status?: string | null): StatusVariant => {
  const key = normalizeStatusKey(status);
  if (!key) return 'muted';
  return STATUS_VARIANTS[key as keyof typeof STATUS_VARIANTS] ?? 'muted';
};
