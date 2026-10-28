// Observability (core-service /observability and /activity/search, platform administrators)
import type { FetchLike } from './client';
import { apiGet, apiGetData } from './client';
import type { HealthStatus } from './infrastructure';

export type ObsPeriod = '24h' | '7d' | '30d';

export type ObsAlertGroup = {
  alert_type: string;
  title: string;
  severity: string;
  count: number;
  scopes: string[];
  scope_count: number;
  example: string | null;
  last_seen_at: string | null;
};

export type ObsJob = {
  id: number;
  job_type: string;
  action: string | null;
  status: string;
  error_code: string | null;
  error_message: string | null;
  identity_source_id: number | null;
  updated_at: string | null;
};

export type ObsHealthFamily = { key: string; total: number; up: number; down: number; degraded: number; unknown: number; status: HealthStatus };

export type ObsOverview = {
  period: ObsPeriod;
  health: {
    summary: Record<HealthStatus, number> & { total: number };
    families: ObsHealthFamily[];
    down: { component: string; label: string; message: string | null }[];
    degraded: { component: string; label: string; message: string | null }[];
    last_check_at: string | null;
    next_check_at: string | null;
    uptime_24h: number | null;
  };
  alerts: { critical_open: number; critical_new: number; warnings_open: number; acknowledged: number; groups: ObsAlertGroup[] };
  jobs: { total: number; failed: number; stuck: number; items: ObsJob[] };
  sign_ins: { total: number; refused: number; reasons: Record<string, number>; unavailable?: boolean };
  events: Record<string, unknown>[];
};

export const getObservabilityOverview = (fetchFn: FetchLike, period: ObsPeriod) =>
  apiGetData<ObsOverview>(fetchFn, '/observability/overview', { period });

export type EventSearch = {
  page: number;
  page_size: number;
  period?: ObsPeriod | '';
  module?: string;
  severity?: string;
  outcome?: '' | 'success' | 'failure';
  actor?: string;
  q?: string;
};

export type EventSearchResult = {
  items: Record<string, unknown>[];
  total: number;
  page: number;
  page_size: number;
  modules: string[];
};

export async function searchEvents(fetchFn: FetchLike, params: EventSearch): Promise<EventSearchResult> {
  const query = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null));
  const res = await apiGet<{ data?: Record<string, unknown>[]; meta?: Record<string, unknown> }>(fetchFn, '/activity/search', query as Record<string, string | number>);
  const meta = res?.meta ?? {};
  return {
    items: Array.isArray(res?.data) ? res.data : [],
    total: Number(meta.total ?? 0),
    page: Number(meta.page ?? params.page),
    page_size: Number(meta.page_size ?? params.page_size),
    modules: Array.isArray(meta.modules) ? (meta.modules as string[]) : []
  };
}
