import { apiGetList, type FetchLike } from './client';

export type HealthEntityType = 'identity_source' | 'storage_endpoint' | 'storage_root';

export type HealthSummaryDay = {
  date: string;
  status: 'success' | 'running' | 'warning' | 'failed' | 'unknown' | string;
  severity: 'info' | 'warning' | 'critical' | string;
  checks: number;
  failures: number;
  warnings: number;
  message?: string | null;
  last_checked_at?: string | null;
};

export const getHealthSummary = (
  fetchFn: FetchLike,
  entityType: HealthEntityType,
  entityId: number,
  days = 7
) =>
  apiGetList<HealthSummaryDay>(fetchFn, '/health/summary', {
    entity_type: entityType,
    entity_id: Number(entityId),
    days: Number(days)
  });
