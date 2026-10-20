import { t } from '$lib/i18n';
type AccessRequestTone = 'pending' | 'approved' | 'rejected' | 'revoked' | 'enforced' | 'neutral';

type AccessRequestStatusMeta = {
  label: string;
  tone: AccessRequestTone;
};

const REQUEST_STATUS_MAP: Record<string, AccessRequestStatusMeta> = {
  pending: { label: 'Pending', tone: 'pending' },
  approved: { label: 'Approved', tone: 'approved' },
  enforced: { label: 'Enforced', tone: 'enforced' },
  revoked: { label: 'Revoked', tone: 'revoked' },
  rejected: { label: 'Rejected', tone: 'rejected' }
};

const resolveRequestStatusMeta = (status?: string | null): AccessRequestStatusMeta => {
  const raw = String(status ?? '').toLowerCase().trim();
  if (REQUEST_STATUS_MAP[raw]) return REQUEST_STATUS_MAP[raw];

  if (raw.includes('approved') || raw.includes('applied') || raw.includes('success')) {
    return REQUEST_STATUS_MAP.approved;
  }
  if (raw.includes('reject') || raw.includes('deny') || raw.includes('fail') || raw.includes('error')) {
    return REQUEST_STATUS_MAP.rejected;
  }

  return { label: 'Unknown', tone: 'neutral' };
};

// Labels of the table above are translated when read (the table is built once per module)
export const getRequestStatusMeta = (status?: string | null): AccessRequestStatusMeta => {
  const meta = resolveRequestStatusMeta(status);
  return { ...meta, label: t(meta.label) };
};

export const isProvisioningInFlight = (items: any[]): boolean =>
  (items ?? []).some((p: any) => {
    const v = String(p?.status ?? '').toLowerCase();
    return v === 'queued' || v === 'running';
  });
