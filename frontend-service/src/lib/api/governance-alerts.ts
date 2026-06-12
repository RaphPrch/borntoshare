import { apiGetList, type FetchLike } from './client';

export type GovernanceAlertSeverity = 'info' | 'warning' | 'high' | 'critical' | string;
export type GovernanceAlertStatus = 'open' | 'acknowledged' | 'resolved' | string;

export type GovernanceAlert = {
  id?: number | string;
  alert_key?: string;
  scope_type?: string;
  scope_id?: number | string;
  alert_type?: string;
  severity?: GovernanceAlertSeverity;
  status?: GovernanceAlertStatus;
  title?: string;
  message?: string | null;
  source_type?: string | null;
  source_id?: string | number | null;
  zone_id?: number | string | null;
  storage_endpoint_id?: number | string | null;
  storage_root_id?: number | string | null;
  identity_source_id?: number | string | null;
  correlation_id?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  resolved_at?: string | null;
  acknowledged_at?: string | null;
  metadata_json?: Record<string, unknown> | null;
  tone?: 'warning' | 'error';
  [key: string]: unknown;
};

export const listGovernanceAlerts = async (
  fetchFn: FetchLike,
  params: {
    scope_type?: string;
    scope_id?: number | string;
    storage_root_id?: number | string;
    storage_endpoint_id?: number | string;
    status?: GovernanceAlertStatus;
    limit?: number;
  } = {}
): Promise<GovernanceAlert[]> =>
  apiGetList<GovernanceAlert>(fetchFn, '/governance-alerts', {
    status: params.status ?? 'open',
    limit: params.limit ?? 500,
    scope_type: params.scope_type,
    scope_id: params.scope_id,
    storage_root_id: params.storage_root_id,
    storage_endpoint_id: params.storage_endpoint_id
  });

export const listStorageRootGovernanceAlerts = async (
  fetchFn: FetchLike,
  storageRootId: number | string,
  params: { status?: GovernanceAlertStatus; reconcile?: boolean } = {}
): Promise<GovernanceAlert[]> =>
  apiGetList<GovernanceAlert>(fetchFn, `/governance-alerts/storage-roots/${storageRootId}`, {
    status: params.status ?? 'open',
    reconcile: params.reconcile ?? true
  });
