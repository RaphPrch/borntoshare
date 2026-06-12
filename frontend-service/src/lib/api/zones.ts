import {
  apiDeleteData,
  apiGetData,
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

export type ZoneConsole = {
  zone: ZoneOverview;
  endpoints: any[];
  storageRoots: any[];
  /** @deprecated Legacy access-profile payload kept only for DAL response compatibility. */
  accessProfiles: any[];
  provisioningPolicy: ZoneProvisioningPolicy;
  kpis?: { endpoints: number; roots: number; profiles: number } | null;
};

export const getZoneConsole = (fetchFn: FetchLike, zoneId: number): Promise<ZoneConsole> =>
  apiGetData(fetchFn, `/zones/${zoneId}/console`);

/* ==================================================
 * WRITE MODELS (CRUD – modals only)
 * ================================================== */

export type ZoneCreatePayload = {
  name: string;
  code: string;
  description?: string | null;
};

export type ZoneUpdatePayload = Partial<ZoneCreatePayload>;

/* ==================================================
 * READ (UI)
 * ================================================== */

export const listZones = (fetchFn: FetchLike, params: Record<string, any> = {}): Promise<ZoneOverview[]> =>
  apiGetList(fetchFn, "/zones", params);

export const getZoneOverview = (fetchFn: FetchLike, id: number): Promise<ZoneOverview> =>
  apiGetData(fetchFn, `/zones/${id}/overview`);

/** @deprecated Legacy zone access-profile helper kept temporarily for compatibility. */
export const listZoneAccessProfiles = (fetchFn: FetchLike, zoneId: number): Promise<any[]> =>
  apiGetData<any[]>(fetchFn, `/zones/${zoneId}/access-profiles`);

/** @deprecated Legacy zone access-profile helper kept temporarily for compatibility. */
export const attachZoneAccessProfile = (fetchFn: FetchLike, zoneId: number, profileId: number): Promise<{ ok: boolean }> =>
  apiPostData(fetchFn, `/zones/${zoneId}/access-profiles/${profileId}`, {});

/** @deprecated Legacy zone access-profile helper kept temporarily for compatibility. */
export const detachZoneAccessProfile = (fetchFn: FetchLike, zoneId: number, profileId: number): Promise<{ ok: boolean }> =>
  apiDeleteData(fetchFn, `/zones/${zoneId}/access-profiles/${profileId}`);

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

export const getZoneProvisioningPolicy = (fetchFn: FetchLike, zoneId: number): Promise<ZoneProvisioningPolicy> =>
  apiGetData<ZoneProvisioningPolicy>(fetchFn, `/zones/${zoneId}/provisioning-policy`);

export const putZoneProvisioningPolicy = (
  fetchFn: FetchLike,
  zoneId: number,
  payload: Partial<ZoneProvisioningPolicy>
): Promise<ZoneProvisioningPolicy> =>
  apiPutData<ZoneProvisioningPolicy>(fetchFn, `/zones/${zoneId}/provisioning-policy`, payload);
