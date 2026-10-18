import {
  apiDeleteData,
  apiGetList,
  apiPatchData,
  apiPostData,
  apiPutData,
  type FetchLike
} from "./client";

/* ==================================================
 * READ MODELS (UI ONLY – backed by v_zones)
 * ================================================== */

/**
 * ZoneOverview
 * ------------
 * Read-model used by UI pages (Zone page, dashboards).
 * Backed by SQL view: v_zones
 */
export type ZoneOverview = {
  id: number;
  name: string;
  code?: string | null;
  is_active?: boolean | number | null;
  description?: string | null;

  storage_endpoints_count?: number | null;
  storage_roots_count?: number | null;
};

/* ==================================================
 * ZONE CONSOLE
 * ================================================== */

/* ==================================================
 * WRITE MODELS (CRUD – modals only)
 * ================================================== */

export type ZoneCreatePayload = {
  name: string;
  code: string;
  description?: string | null;
};

type ZoneUpdatePayload = Partial<ZoneCreatePayload>;

/* ==================================================
 * READ (UI)
 * ================================================== */

export const listZones = (fetchFn: FetchLike, params: Record<string, any> = {}): Promise<ZoneOverview[]> =>
  apiGetList(fetchFn, "/zones", params);

/* ==================================================
 * WRITE (ADMIN / MODALS)
 * ================================================== */

export const createZone = (fetchFn: FetchLike, payload: ZoneCreatePayload): Promise<{ id: number }> =>
  apiPostData(fetchFn, "/zones", payload);

export const updateZone = (fetchFn: FetchLike, id: number, payload: ZoneUpdatePayload): Promise<{ ok: true }> =>
  apiPatchData(fetchFn, `/zones/${id}`, payload);

export const deleteZone = async (fetchFn: FetchLike, id: number): Promise<void> => {
  await apiDeleteData(fetchFn, `/zones/${id}`);
};

/* ==================================================
 * Provisioning Policy
 * ================================================== */

export type ZoneProvisioningPolicy = {
  zone_id?: number;
  enabled: boolean;
  policy_mode?: "ON_FIRST_ACCESS_REQUEST" | string;
  ou_strategy: "identity_default" | "zone_static";
  base_ou_dn?: string | null;
  static_ou_dn: string | null;
  updated_at?: string | null;
  effective_preview?: {
    effective_identity_source_id: number | null;
    effective_identity_source_name: string | null;
    effective_ou_dn: string | null;
    warnings: string[];
  } | null;
};

export const putZoneProvisioningPolicy = (
  fetchFn: FetchLike,
  zoneId: number,
  payload: Partial<ZoneProvisioningPolicy>
): Promise<ZoneProvisioningPolicy> =>
  apiPutData<ZoneProvisioningPolicy>(fetchFn, `/zones/${zoneId}/provisioning-policy`, payload);
