/* ============================================================
 * Dashboard — Types
 * Aligned with /dashboard/overview
 * ============================================================ */

/* --------------------------------------------
 * Access request status
 * -------------------------------------------- */
export type AccessRequestStatus =
  | "pending"
  | "approved"
  | "rejected";

/* --------------------------------------------
 * Dashboard — User summary (KPI)
 * -------------------------------------------- */
export interface DashboardUserSummary {
  /** Display name resolved by backend */
  user_display_name: string;

  /** Requests grouped by status */
  requests_by_status: {
    pending: number;
    approved: number;
    rejected: number;
  };

  /** @deprecated Legacy KPI still accepted from the API but no longer used as an active dashboard metric. */
  access_profiles_count: number;
}

/* --------------------------------------------
 * Dashboard — Latest access requests
 * -------------------------------------------- */
export interface DashboardLatestRequestRow {
  id: number;

  status: AccessRequestStatus;
  created_at: string;
  updated_at?: string;

  requester_id: number;
  requester_display_name: string;

  storage_root_id: number;
  storage_root_name: string;

  access_profile_id: number | null;

  /** Preferred (when joined) */
  access_profile_code?: string;
  access_profile_label?: string;

  /** Fallback (always present in v_access_requests_status) */
  requested_level?: string;
  requested_level_label?: string;
}

/* --------------------------------------------
 * Dashboard — Effective access
 * -------------------------------------------- */
export interface DashboardEffectiveAccessRow {
  storage_root_id: number;
  storage_root_name?: string;

  access_level: string;
  access_profile_code?: string;

  granted_at: string | null;
  expires_at?: string | null;

  actor_id?: number;
  actor_display_name?: string;

  /** source = access_request | discovery | manual | etc. */
  source?: string;
}


/* --------------------------------------------
 * Dashboard — Overview payload
 * -------------------------------------------- */
export interface DashboardOverview {
  summary: DashboardUserSummary;
  latest_requests: DashboardLatestRequestRow[];
  effective_access: DashboardEffectiveAccessRow[];
}
