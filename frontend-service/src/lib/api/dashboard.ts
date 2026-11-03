import type { RequestEvent } from '@sveltejs/kit';

import { apiGetData, type FetchLike } from "$lib/api/client";
import { apiServerGetData } from '$lib/server/api-server';

export type DashboardRequest = {
  request_id?: number;
  request_code?: string | null;
  status?: string | null;
  status_label?: string | null;
  storage_root_id?: number | null;
  storage_root_name?: string | null;
  target_path?: string | null;
  permission?: string | null;
  expires_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  requested_for_display?: string | null;
  latest_execution_status?: string | null;
  overdue?: boolean | null;
};

export type UserDashboardMePayload = {
  role: 'user' | 'guardian';
  mine: { pending: number; active: number; ending_30d: number; failed: number; refused_30d: number };
  my_requests: DashboardRequest[];
  my_ending: DashboardRequest[];
  guardian?: {
    folders: number;
    folders_with_alerts: number;
    to_decide: number;
    overdue: number;
    failed: number;
    active: number;
    ending_30d: number;
    approved_30d?: number;
    refused_30d?: number;
    revoked_30d?: number;
  };
  to_decide?: DashboardRequest[];
  guarded_failed?: DashboardRequest[];
};

/* ==================================================
 * READ — AGGREGATED DASHBOARD (SSR SAFE)
 * ================================================== */

/* ==================================================
 * READ — ADMIN KPI (PLATFORM)
 * ================================================== */

type DashboardPlatformOverview = {
  zones_count?: number;
  storage_endpoints_count?: number;
  storage_roots_count?: number;
  tags_count?: number;
  /** @deprecated Legacy KPI still accepted from the API but not displayed as an active metric. */
  access_profiles_count?: number;
  access_requests_count?: number;

  // enriched fields
  admins_count?: number;
  pending_requests_count?: number;

  open_alerts_count?: number;
  critical_alerts_count?: number;
  failed_jobs_24h_count?: number;
  stale_pending_requests_count?: number;
  requests_last_30_days?: { day: string; submitted: number; applied: number }[];

  // backend convenience mapping
  storage_roots?: number;
  storage_endpoints?: number;
  admins?: number;
  pending_requests?: number;
};

export async function getDashboardPlatformOverviewServer(
  event: RequestEvent
): Promise<DashboardPlatformOverview> {
  const raw = await apiServerGetData<DashboardPlatformOverview>(
    '/dashboard/platform-overview',
    event
  );

  return {
    ...raw,
    storage_roots:
      raw?.storage_roots ?? raw?.storage_roots_count ?? 0,
    storage_endpoints:
      raw?.storage_endpoints ?? raw?.storage_endpoints_count ?? 0,
    admins: raw?.admins ?? raw?.admins_count ?? 0,
    pending_requests:
      raw?.pending_requests ?? raw?.pending_requests_count ?? 0
  };
}

export async function getUserDashboardMe(fetchFn: FetchLike): Promise<UserDashboardMePayload> {
  const raw = await apiGetData<Partial<UserDashboardMePayload>>(fetchFn, '/dashboard/me');
  const list = (value: unknown) => (Array.isArray(value) ? (value as DashboardRequest[]) : []);
  return {
    role: raw?.role === 'guardian' ? 'guardian' : 'user',
    mine: { pending: 0, active: 0, ending_30d: 0, failed: 0, refused_30d: 0, ...(raw?.mine ?? {}) },
    my_requests: list(raw?.my_requests),
    my_ending: list(raw?.my_ending),
    ...(raw?.guardian ? { guardian: raw.guardian, to_decide: list(raw?.to_decide), guarded_failed: list(raw?.guarded_failed) } : {})
  };
}

/* ==================================================
 * OPTIONAL — DIRECT ENDPOINTS (ADVANCED UI, SSR SAFE)
 * ================================================== */
