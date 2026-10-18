import type { RequestEvent } from '@sveltejs/kit';

import { apiGetData, type FetchLike } from "$lib/api/client";
import { apiServerGetData } from '$lib/server/api-server';

type UserDashboardMeSummary = {
  my_open_requests: number;
  awaiting_my_review: number;
  approved: number;
  rejected_or_closed: number;
};

type UserDashboardMeRequest = Record<string, unknown> & {
  request_id?: number;
  request_code?: string;
  storage_root_id?: number;
  storage_root_name?: string;
  requested_for_display?: string;
  access_profile_name?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  viewer_role?: string;
  is_requester?: boolean;
  is_guardian?: boolean;
};

type UserDashboardMePayload = {
  summary: UserDashboardMeSummary;
  requires_action: UserDashboardMeRequest[];
  visible_requests: UserDashboardMeRequest[];
};

const DEFAULT_USER_DASHBOARD_ME: UserDashboardMePayload = {
  summary: {
    my_open_requests: 0,
    awaiting_my_review: 0,
    approved: 0,
    rejected_or_closed: 0
  },
  requires_action: [],
  visible_requests: []
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

export async function getUserDashboardMe(
  fetchFn: FetchLike
): Promise<UserDashboardMePayload> {
  const raw = await apiGetData<Partial<UserDashboardMePayload>>(fetchFn, "/dashboard/me");
  const summary = raw?.summary ?? {};
  return {
    summary: {
      my_open_requests: Number(summary.my_open_requests ?? 0),
      awaiting_my_review: Number(summary.awaiting_my_review ?? 0),
      approved: Number(summary.approved ?? 0),
      rejected_or_closed: Number(summary.rejected_or_closed ?? 0)
    },
    requires_action: Array.isArray(raw?.requires_action) ? raw!.requires_action : DEFAULT_USER_DASHBOARD_ME.requires_action,
    visible_requests: Array.isArray(raw?.visible_requests) ? raw!.visible_requests : DEFAULT_USER_DASHBOARD_ME.visible_requests
  };
}

/* ==================================================
 * OPTIONAL — DIRECT ENDPOINTS (ADVANCED UI, SSR SAFE)
 * ================================================== */
