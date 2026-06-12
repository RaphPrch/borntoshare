import type { FetchLike } from './client';
import { apiGetList, apiGetData, apiPostData } from './client';

type AccessRequestContextResponse = {
  requests: unknown[];
  tabCounts: Record<string, number>;
};

type AccessRequestRecord = Record<string, unknown>;

export type BulkDecisionResponse = {
  ok: boolean;
  decision: 'approve' | 'reject' | 'revoke' | string;
  requested_ids: number[];
  updated_ids: number[];
  failed_ids: number[];
  failed_reasons: Record<number, string>;
  failed_details?: Record<
    number,
    {
      item_id?: number | null;
      code?: string | null;
      message?: string | null;
      hint?: string | null;
      storage_root_id?: number | null;
      requested_permission?: string | null;
      candidates_count?: number;
    }
  >;
  updated_count: number;
  executions_started: number;
};

const toInt = (value: unknown, fallback = 0): number => {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};

const toIntArray = (value: unknown): number[] => {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item));
};

const toFailedReasonsMap = (value: unknown): Record<number, string> => {
  if (!value || typeof value !== 'object') return {};
  const entries = Object.entries(value as Record<string, unknown>);
  const out: Record<number, string> = {};
  for (const [k, v] of entries) {
    const id = Number(k);
    if (!Number.isFinite(id)) continue;
    const reason = String(v ?? '').trim();
    if (!reason) continue;
    out[id] = reason;
  }
  return out;
};

const normalizeBulkDecisionResponse = (raw: unknown): BulkDecisionResponse => {
  const payload = raw ?? {};
  const record = payload as Record<string, unknown>;

  const failedDetails = (() => {
    const source = record.failed_details;
    if (!source || typeof source !== 'object') return {};
    const out: Record<number, Record<string, unknown>> = {};
    for (const [k, v] of Object.entries(source as Record<string, unknown>)) {
      const id = Number(k);
      if (!Number.isFinite(id) || !v || typeof v !== 'object') continue;
      out[id] = v as Record<string, unknown>;
    }
    return out;
  })();

  return {
    ok: Boolean(record.ok),
    decision: String(record.decision ?? ''),
    requested_ids: toIntArray(record.requested_ids),
    updated_ids: toIntArray(record.updated_ids),
    failed_ids: toIntArray(record.failed_ids),
    failed_reasons: toFailedReasonsMap(record.failed_reasons),
    failed_details: failedDetails,
    updated_count: toInt(record.updated_count),
    executions_started: toInt(record.executions_started),
  };
};

export type CreateAccessRequestPayload = {
  code?: string;
  requester_identity_id?: number;
  storage_root_id: number;
  permissions: string[];
  expires_at?: string | null;
  justification: string;
  requested_principal?: {
    id?: string | number | null;
    external_id?: string | null;
    dn?: string | null;
    username?: string | null;
    display_name?: string | null;
    email?: string | null;
    auth_source?: string | null;
    type?: string | null;
    identity_source_id?: number | null;
  };
};

export type CheckExistingAccessPayload = {
  storage_root_id: number;
  permission?: string;
  access_level?: string;
  requester_identity_id?: number;
  requested_principal?: CreateAccessRequestPayload['requested_principal'];
};

export type CheckExistingAccessResponse = {
  can_request: boolean;
  current_access_level: 'NONE' | 'READ' | 'WRITE' | string;
  code?: 'NONE' | 'ACCESS_ALREADY_GRANTED' | 'ACCESS_REQUEST_ALREADY_EXISTS' | 'ELEVATION_ALLOWED' | 'INVALID_ACCESS_LEVEL' | string;
  reason: 'NONE' | 'ACCESS_ALREADY_GRANTED' | 'ACCESS_REQUEST_ALREADY_EXISTS' | 'ELEVATION_ALLOWED' | 'INVALID_ACCESS_LEVEL' | string;
  message: string;
  source?: 'DB' | 'IDENTITY_SNAPSHOT' | 'EFFECTIVE_ACCESS' | 'AD' | 'UNKNOWN' | string;
  access_request_id?: number | null;
  access_request_code?: string | null;
};

/**
 * LIST access requests (optionnellement filtrées par status)
 */
export const listAccessRequests = (
  fetchFn: FetchLike,
  q?: {
    status?: string;
    my_action?: number;
    overdue?: number;
    high_impact?: number;
    query?: string;
  }
) => {
  const params = new URLSearchParams();

  if (q?.status) {
    params.set('status', q.status);
  }
  if (q?.my_action !== undefined) {
    params.set('my_action', String(q.my_action));
  }
  if (q?.overdue !== undefined) {
    params.set('overdue', String(q.overdue));
  }
  if (q?.high_impact !== undefined) {
    params.set('high_impact', String(q.high_impact));
  }
  if (q?.query) {
    params.set('q', q.query);
  }

  const qs = params.toString();
  return apiGetList<AccessRequestRecord>(fetchFn, `/access-requests${qs ? `?${qs}` : ''}`);
};

/**
 * GET one access request by id
 */
export const getAccessRequestDetails = (
  fetchFn: FetchLike,
  id: string | number
) => {
  return apiGetData<AccessRequestRecord>(fetchFn, `/access-requests/${id}`);
};

export const checkExistingAccess = (
  fetchFn: FetchLike,
  payload: CheckExistingAccessPayload
) => {
  return apiPostData<CheckExistingAccessResponse>(fetchFn, '/access-requests/check-existing-access', payload);
};

/**
 * APPROVE an access request
 */
export const bulkDecision = async (
  fetchFn: FetchLike,
  ids: number[],
  decision: 'approve' | 'reject' | 'revoke',
  decisionComment?: string
) => {
  const comment = String(decisionComment || '').trim();
  const response = await apiPostData<Record<string, unknown>>(fetchFn, '/access-requests/bulk', {
    ids,
    decision,
    ...(comment ? { decision_comment: comment } : {})
  });

  return normalizeBulkDecisionResponse(response);
};

export const getAccessRequestCountsByStatus = (
  fetchFn: FetchLike,
  q?: {
    my_action?: number;
    overdue?: number;
    high_impact?: number;
    query?: string;
  }
) => {
  const params = new URLSearchParams();

  if (q?.my_action !== undefined) {
    params.set('my_action', String(q.my_action));
  }
  if (q?.overdue !== undefined) {
    params.set('overdue', String(q.overdue));
  }
  if (q?.high_impact !== undefined) {
    params.set('high_impact', String(q.high_impact));
  }
  if (q?.query) {
    params.set('q', q.query);
  }

  const qs = params.toString();
  return apiGetData<Record<string, number>>(
    fetchFn,
    `/access-requests/counts-by-status${qs ? `?${qs}` : ''}`
  );
};

/**
 * Context endpoint (backend BFF)
 * Retourne en un seul appel la liste et les compteurs d'onglets.
 */
export const getAccessRequestsContext = (
  fetchFn: FetchLike,
  q?: {
    status?: string;
    my_action?: number;
    overdue?: number;
    high_impact?: number;
    query?: string;
  }
) => {
  const params = new URLSearchParams();

  if (q?.status) params.set('status', q.status);
  if (q?.my_action !== undefined) params.set('my_action', String(q.my_action));
  if (q?.overdue !== undefined) params.set('overdue', String(q.overdue));
  if (q?.high_impact !== undefined) params.set('high_impact', String(q.high_impact));
  if (q?.query) params.set('q', q.query);

  const requestQs = params.toString();

  const countsParams = new URLSearchParams(params);
  countsParams.delete('status');
  const countsQs = countsParams.toString();

  return Promise.all([
    apiGetList<AccessRequestRecord>(fetchFn, `/access-requests${requestQs ? `?${requestQs}` : ''}`),
    apiGetData<Record<string, number>>(
      fetchFn,
      `/access-requests/counts-by-status${countsQs ? `?${countsQs}` : ''}`
    )
  ]).then(([requests, tabCounts]) => ({ requests, tabCounts }));
};

/**
 * CREATE a new access request
 */
export const createAccessRequest = (
  fetchFn: FetchLike,
  payload: CreateAccessRequestPayload
) => {
  return apiPostData<{ id: number }>(fetchFn, '/access-requests', payload);
};
