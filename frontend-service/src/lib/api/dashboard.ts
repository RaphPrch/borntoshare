import type { RequestEvent } from '@sveltejs/kit';

import { apiGetData, apiGetList, type FetchLike } from "$lib/api/client";
import { apiServerGetData } from '$lib/server/api-server';

import type {
  DashboardUserSummary,
  DashboardLatestRequestRow,
  DashboardEffectiveAccessRow
} from "$lib/types/dashboard";

/* ==================================================
 * READ MODEL (UI CONTRACT)
 * ================================================== */

export type DashboardOverview = {
  summary: DashboardUserSummary;
  latest_requests: DashboardLatestRequestRow[];
  effective_access: DashboardEffectiveAccessRow[];
};

export type UserDashboardMeSummary = {
  my_open_requests: number;
  awaiting_my_review: number;
  approved: number;
  rejected_or_closed: number;
};

export type UserDashboardMeRequest = Record<string, unknown> & {
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

export type UserDashboardMePayload = {
  summary: UserDashboardMeSummary;
  requires_action: UserDashboardMeRequest[];
  visible_requests: UserDashboardMeRequest[];
};

/* ==================================================
 * DEFAULTS (UI NEVER BREAKS)
 * ================================================== */

const DEFAULT_SUMMARY: DashboardUserSummary = {
  user_display_name: "User",
  requests_by_status: {
    pending: 0,
    approved: 0,
    rejected: 0
  },
  // Deprecated KPI kept only so older DAL payloads still normalize safely.
  access_profiles_count: 0
};

const DEFAULT_OVERVIEW: DashboardOverview = {
  summary: DEFAULT_SUMMARY,
  latest_requests: [],
  effective_access: []
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
 * SAFE HELPERS
 * ================================================== */

function asArray<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

function asObject(v: unknown): Record<string, any> {
  return v && typeof v === "object" ? (v as Record<string, any>) : {};
}

/* ==================================================
 * NORMALIZATION (STRICT UI CONTRACT)
 * ================================================== */

export function normalizeDashboardOverview(
  payload: unknown
): DashboardOverview {
  const root = asObject(payload);
  const o = root.overview ? asObject(root.overview) : root;

  const summaryRaw = asObject(o.summary);
  const reqByStatus = asObject(summaryRaw.requests_by_status);

  const summary: DashboardUserSummary = {
    ...DEFAULT_SUMMARY,
    ...summaryRaw,
    requests_by_status: {
      pending: Number(
        reqByStatus.pending ?? DEFAULT_SUMMARY.requests_by_status.pending
      ),
      approved: Number(
        reqByStatus.approved ?? DEFAULT_SUMMARY.requests_by_status.approved
      ),
      rejected: Number(
        reqByStatus.rejected ?? DEFAULT_SUMMARY.requests_by_status.rejected
      )
    },
    access_profiles_count: Number(
      summaryRaw.access_profiles_count ??
        DEFAULT_SUMMARY.access_profiles_count
    )
  };

  return {
    summary,
    latest_requests: asArray<DashboardLatestRequestRow>(o.latest_requests),
    effective_access: asArray<DashboardEffectiveAccessRow>(o.effective_access)
  };
}

/* ==================================================
 * READ — AGGREGATED DASHBOARD (SSR SAFE)
 * ================================================== */

/**
 * Dashboard overview (aggregated by backend).
 *
 * Backed by:
 * - GET /dashboard/overview
 *
 * SSR rules:
 * - cookie MUST be forwarded
 * - never returns null
 * - UI-safe
 */
export async function getDashboardOverview(
  fetchFn: FetchLike,
  cookie: string
): Promise<DashboardOverview> {
  // NOTE:
  // SvelteKit SSR `fetch` already forwards cookies for same-origin calls.
  // Passing headers via apiGet() would be treated as query params (see request() signature).
  void cookie;

  const raw = await apiGetData(fetchFn, "/dashboard/overview");

  return normalizeDashboardOverview(raw ?? DEFAULT_OVERVIEW);
}

/* ==================================================
 * READ — ADMIN KPI (PLATFORM)
 * ================================================== */

export type DashboardPlatformOverview = {
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

export async function getDashboardPlatformOverview(
  fetchFn: FetchLike,
  cookie: string
): Promise<DashboardPlatformOverview> {
  void cookie;
  const raw = await apiGetData<DashboardPlatformOverview>(
    fetchFn,
    "/dashboard/platform-overview"
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

export async function getDashboardLatestRequests(
  fetchFn: FetchLike,
  cookie: string,
  opts?: { limit?: number; status?: string; days?: number }
): Promise<DashboardLatestRequestRow[]> {
  const params = new URLSearchParams();

  if (opts?.limit) params.set("limit", String(opts.limit));
  if (opts?.status) params.set("status", opts.status);
  if (opts?.days) params.set("days", String(opts.days));

  const qs = params.toString() ? `?${params.toString()}` : "";
  void cookie;
  return apiGetList<DashboardLatestRequestRow>(fetchFn, `/dashboard/user-latest-requests${qs}`);
}

export async function getDashboardEffectiveAccess(
  fetchFn: FetchLike,
  cookie: string,
  opts?: { limit?: number }
): Promise<DashboardEffectiveAccessRow[]> {
  const params = new URLSearchParams();
  if (opts?.limit) params.set("limit", String(opts.limit));

  const qs = params.toString() ? `?${params.toString()}` : "";
  void cookie;
  return apiGetList<DashboardEffectiveAccessRow>(fetchFn, `/dashboard/user-effective-access${qs}`);
}
