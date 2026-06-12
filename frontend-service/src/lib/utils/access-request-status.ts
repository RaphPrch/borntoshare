import {
  deriveAccessRequestBusinessState,
  mapAccessRequestOverallToVariant
} from '$lib/services/mappers/visual-state.mapper';

export type AccessRequestTone = 'pending' | 'approved' | 'rejected' | 'revoked' | 'enforced' | 'neutral';

export type AccessRequestStatusMeta = {
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

export const getRequestStatusMeta = (status?: string | null): AccessRequestStatusMeta => {
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

export const getProvisioningStatusMeta = (status?: string | null): AccessRequestStatusMeta => {
  const raw = String(status ?? '').toLowerCase().trim();
  if (raw === 'success') return { label: 'Success', tone: 'approved' };
  if (raw === 'failed' || raw === 'error') return { label: 'Failed', tone: 'rejected' };
  if (raw === 'running') return { label: 'Running', tone: 'pending' };
  if (raw === 'queued') return { label: 'Queued', tone: 'pending' };
  if (raw === 'revoked') return { label: 'Revoked', tone: 'revoked' };
  if (raw === 'enforced') return { label: 'Enforced', tone: 'enforced' };
  return { label: 'Unknown', tone: 'neutral' };
};

export const getRequestOverallVariant = (status?: string | null) => {
  const business = deriveAccessRequestBusinessState({ workflowStatus: status });
  return mapAccessRequestOverallToVariant(business.overall);
};

export const isProvisioningInFlight = (items: any[]): boolean =>
  (items ?? []).some((p: any) => {
    const v = String(p?.status ?? '').toLowerCase();
    return v === 'queued' || v === 'running';
  });

export const ACCESS_REQUEST_TABS = ['pending', 'approved', 'enforced', 'revoked', 'rejected'] as const;
