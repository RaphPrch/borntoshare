import { apiDeleteData, apiGetData, apiPostData, apiPutData } from './client';

type Fetch = typeof fetch;

/** FSRM quota of a governed folder, as the file server answered on its last reading */
export type FolderQuota = {
  status: 'pending' | 'applied' | 'none' | 'failed';
  limit_bytes: number | null;
  soft: boolean;
  warn_percent: number;
  used_bytes: number | null;
  peak_bytes: number | null;
  used_percent: number | null;
  local_path: string | null;
  server_status: string | null;
  pending_operation: 'set' | 'remove' | 'read' | null;
  error_code: string | null;
  error_message: string | null;
  read_at: string | null;
  applied_at: string | null;
  updated_by: string | null;
};

export type QuotaRequest = {
  id: number;
  storage_root_id: number;
  requested_by_identity_id: number | null;
  requested_by: string | null;
  current_limit_bytes: number | null;
  requested_limit_bytes: number;
  reason: string;
  status: 'pending' | 'approved' | 'rejected' | 'cancelled';
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string | null;
  folder_name?: string;
  root_path?: string;
};

export type FolderQuotaState = { quota: FolderQuota | null; pending_request: QuotaRequest | null; requests: QuotaRequest[] };

export const getFolderQuota = (fetchFn: Fetch, rootId: number) => apiGetData<FolderQuotaState>(fetchFn, `/storage-roots/${rootId}/quota`);

export const setFolderQuota = (fetchFn: Fetch, rootId: number, body: { limit_bytes: number; soft: boolean; warn_percent: number }) =>
  apiPutData<FolderQuotaState>(fetchFn, `/storage-roots/${rootId}/quota`, body);

export const removeFolderQuota = (fetchFn: Fetch, rootId: number) => apiDeleteData<FolderQuotaState>(fetchFn, `/storage-roots/${rootId}/quota`);

export const refreshFolderQuota = (fetchFn: Fetch, rootId: number) => apiPostData<FolderQuotaState>(fetchFn, `/storage-roots/${rootId}/quota/refresh`, {});

export const requestMoreQuota = (fetchFn: Fetch, rootId: number, body: { requested_limit_bytes: number; reason: string }) =>
  apiPostData<FolderQuotaState>(fetchFn, `/storage-roots/${rootId}/quota/requests`, body);

export const decideQuotaRequest = (fetchFn: Fetch, requestId: number, body: { decision: 'approve' | 'reject' | 'cancel'; note?: string | null }) =>
  apiPostData<FolderQuotaState>(fetchFn, `/quota-requests/${requestId}/decision`, body);

export const listQuotaRequests = (fetchFn: Fetch, status: 'pending' | 'all' = 'pending') =>
  apiGetData<QuotaRequest[]>(fetchFn, '/quota-requests', { status_filter: status });
