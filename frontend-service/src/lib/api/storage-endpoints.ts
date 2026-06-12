import {
  apiDeleteData,
  apiGetData,
  apiGetList,
  apiPatchData,
  apiPostData,
  apiPutData,
  type FetchLike
} from './client';

/* ==================================================
 * TYPES
 * ================================================== */

export type StorageProtocol =
  | 'smb'
  | 'nfs'
  | 's3'
  | 'azure_blob'
  | string;

/* ==================================================
 * READ MODELS
 * ================================================== */

/**
 * Context view (DAL / governance / sidebar)
 * Source of truth: SQL view (contractual)
 */
export type StorageEndpointContext = {
  storage_endpoint_id: number;
  storage_endpoint_name: string;
  storage_endpoint_type: StorageProtocol;
  protocol?: string | null;

  host?: string | null;
  port?: number | null;

  bind_dn?: string | null;
  bind_password_ref?: string | null;

  auth_username?: string | null;
  auth_secret_ref?: string | null;

  status?: string | null;
  last_probe_status?: string | null;
  last_probe_at?: string | null;
  last_probe_message?: string | null;
  operational_state?: 'reachable' | 'checking' | 'unreachable' | 'disabled' | 'unknown' | string | null;
  pending_requests_count?: number | null;
  is_active: boolean;

  zone_id?: number | null;
  zone_name?: string | null;
  roots_count?: number | null;
};

/**
 * UI Overview (normalized for frontend)
 * ⚠️ No business logic, projection only
 */
export type StorageEndpointOverview = {
  id: number;
  name: string;
  type: StorageProtocol;
  protocol?: string | null;

  host?: string | null;
  port?: number | null;

  bind_dn?: string | null;
  bind_password_ref?: string | null;

  auth_username?: string | null;
  auth_secret_ref?: string | null;

  status?: string | null;
  last_probe_status?: string | null;
  last_probe_at?: string | null;
  last_probe_message?: string | null;
  operational_state?: 'reachable' | 'checking' | 'unreachable' | 'disabled' | 'unknown' | string | null;
  pending_requests_count?: number | null;

  is_active: boolean;

  zone_id?: number | null;
  zone_name?: string | null;
  roots_count?: number | null;

  /** Optional UI enrichment */
  tags?:
    | Array<{
        id: number;
        name?: string;
        label: string;
        code?: string;
        color_rgb?: string | null;
        value_text?: string | null;
      }>
    | string[];
};

export type StorageEndpointProvisioningPolicy = {
  storage_endpoint_id: number;
  storage_endpoint_name?: string | null;
  zone_id: number | null;
  zone_name?: string | null;
  endpoint_type?: string | null;
  host?: string | null;

  policy_mode: 'inherit' | 'override';
  endpoint_override_enabled: boolean;

  policy_source: 'zone' | 'endpoint' | 'global' | 'none';
  policy_source_label: string;

  endpoint_values: {
    ou_dn: string | null;
    naming_template: string | null;
  };
  inherited_values: {
    ou_dn: string | null;
    naming_template: string | null;
  };
  effective_values: {
    ou_dn: string | null;
    naming_template: string | null;
  };

  effective_ou_status: 'configured' | 'missing';
  effective_template_status: 'configured' | 'missing';

  configuration_status: 'ready' | 'warning' | 'incomplete';
  configuration_message: string;
  is_ready_to_provision: boolean;

  warnings: Array<{
    code: string;
    level: 'info' | 'warning' | 'error';
    message: string;
  }>;

  example_groups?: {
    based_on_root_code?: string | null;
    read?: string | null;
    write?: string | null;
  } | null;

  effective_naming_policy?: {
    group_prefix?: string | null;
    template?: string | null;
    normalize_uppercase?: boolean | null;
    max_sam_length?: number | null;
    rootcode_strategy?: string | null;
  } | null;

  effective_identity_source?: {
    id: number | null;
    name: string | null;
  };
};

export type StorageEndpointProvisioningUpdatePayload = {
  policy_mode: 'inherit' | 'override';
  endpoint_values?: {
    ou_dn?: string | null;
    naming_template?: string | null;
  };
};

export type StorageEndpointDetail = StorageEndpointOverview & {
  description?: string | null;
  identity_source_id?: number | null;
  config_json?: Record<string, unknown> | null;
};

type StorageEndpointCreateResponse = {
  id?: number;
  storage_endpoint_id?: number;
};

export type StorageEndpointProbeResultPayload = {
  last_probe_status: 'success' | 'failed' | 'running' | 'unknown' | string;
  last_probe_at?: string | null;
  last_probe_message?: string | null;
  last_probe_job_id?: number | null;
  source_type?: string | null;
};

export type StorageEndpointProbeResultResponse = {
  storage_endpoint_id: number;
  last_probe_status: string;
  last_probe_at: string;
  last_probe_message?: string | null;
  impacted_roots?: Array<Record<string, unknown>>;
};

/* ==================================================
 * READ (UI SAFE)
 * ================================================== */

/**
 * LIST — UI SAFE
 *
 * Contract:
 * - 200 => list
 * - 404 => no storage endpoints configured (VALID STATE)
 */
export const listStorageEndpoints = async (
  fetchFn: FetchLike
): Promise<StorageEndpointOverview[]> => {
  try {
    const rows = await apiGetList<StorageEndpointContext>(fetchFn, '/storage-endpoints/context');

    const mapped: StorageEndpointOverview[] = [];
    for (const row of rows as StorageEndpointContext[]) {
      mapped.push({
        id: row.storage_endpoint_id,
        name: row.storage_endpoint_name,
        type: row.storage_endpoint_type,
        protocol: row.protocol ?? row.storage_endpoint_type ?? null,

        host: row.host ?? null,
        port: row.port ?? null,

        bind_dn: row.bind_dn ?? null,
        bind_password_ref: row.bind_password_ref ?? null,
        auth_username: row.auth_username ?? row.bind_dn ?? null,
        auth_secret_ref: row.auth_secret_ref ?? row.bind_password_ref ?? null,

        status: row.status ?? null,
        last_probe_status: row.last_probe_status ?? null,
        last_probe_at: row.last_probe_at ?? null,
        last_probe_message: row.last_probe_message ?? null,
        operational_state: row.operational_state ?? null,
        pending_requests_count: row.pending_requests_count ?? null,
        is_active: row.is_active,

        zone_id: row.zone_id ?? null,
        zone_name: row.zone_name ?? null,
        roots_count: row.roots_count ?? null
      });
    }

    return mapped;
  } catch (err: any) {
    if (err?.status === 404) {
      // ✅ valid state: no storage endpoints yet
      return [];
    }
    throw err;
  }
};

/**
 * Single endpoint overview
 *
 * ⚠️ 404 must be handled by caller (detail page)
 */
export const getStorageEndpointOverview = async (
  fetchFn: FetchLike,
  id: number
): Promise<StorageEndpointOverview> => {
  return apiGetData<StorageEndpointOverview>(fetchFn, `/storage-endpoints/${id}/overview`);
};

/**
 * Full storage endpoint detail (edit page)
 */
export const getStorageEndpoint = async (
  fetchFn: FetchLike,
  id: number
): Promise<StorageEndpointDetail> =>
  apiGetData<StorageEndpointDetail>(fetchFn, `/storage-endpoints/${id}`);

export const getStorageEndpointProvisioningPolicy = async (
  fetchFn: FetchLike,
  id: number
): Promise<StorageEndpointProvisioningPolicy> => {
  return apiGetData<StorageEndpointProvisioningPolicy>(
    fetchFn,
    `/storage-endpoints/${id}/provisioning-policy`
  );
};

export const putStorageEndpointProvisioningPolicy = async (
  fetchFn: FetchLike,
  id: number,
  payload: StorageEndpointProvisioningUpdatePayload
): Promise<StorageEndpointProvisioningPolicy> => {
  return apiPutData<StorageEndpointProvisioningPolicy>(
    fetchFn,
    `/storage-endpoints/${id}/provisioning-policy`,
    payload
  );
};

/* ==================================================
 * WRITE (CRUD — GOVERNANCE SCOPE)
 * ================================================== */

export type StorageEndpointCreatePayload = {
  name: string;
  description?: string | null;
  endpoint_type: StorageProtocol;
  type?: StorageProtocol;
  protocol?: string | null;
  identity_source_id?: number | null;

  host?: string | null;
  port?: number | null;

  auth_type?: string | null;
  bind_dn?: string | null;
  bind_password_ref?: string | null;

  zone_id: number;

  is_active?: boolean;

  status?: string | null;
  last_probe_status?: string | null;
  last_probe_at?: string | null;
  last_probe_message?: string | null;
};

export type StorageEndpointDalWritePayload = {
  name: string;
  endpoint_type: StorageProtocol;
  zone_id: number;
  description?: string | null;
  identity_source_id?: number | null;
  protocol?: string | null;
  host?: string | null;
  port?: number | null;
  auth_type?: string | null;
  bind_dn?: string | null;
  bind_password_ref?: string | null;
  is_active?: boolean;
  status?: 'active' | 'inactive' | string | null;
  last_probe_status?: string | null;
  last_probe_at?: string | null;
  last_probe_message?: string | null;
};

export type StorageEndpointUpdatePayload =
  Partial<Omit<StorageEndpointCreatePayload, 'zone_id'>> & {
    zone_id?: number | null;
    auth_username?: string | null;
    config_json?: Record<string, any> | null;
  };

type StorageEndpointDalUpdatePayload = Partial<StorageEndpointDalWritePayload> & {
  zone_id?: number | null;
};

function toStorageEndpointCreateDalPayload(payload: StorageEndpointCreatePayload): StorageEndpointDalWritePayload {
  const zoneId = Number(payload.zone_id);
  if (!Number.isInteger(zoneId) || zoneId <= 0) {
    throw new Error('A zone is required to create a storage endpoint.');
  }

  return {
    name: payload.name,
    endpoint_type: payload.endpoint_type,
    zone_id: zoneId,
    description: payload.description ?? null,
    identity_source_id: payload.identity_source_id ?? null,
    protocol: payload.protocol ?? payload.endpoint_type,
    host: payload.host ?? null,
    port: payload.port ?? null,
    auth_type: payload.auth_type ?? null,
    bind_dn: payload.bind_dn ?? null,
    bind_password_ref: payload.bind_password_ref ?? null,
    is_active: payload.is_active ?? true,
    status: payload.status ?? 'active',
    last_probe_status: payload.last_probe_status ?? null,
    last_probe_at: payload.last_probe_at ?? null,
    last_probe_message: payload.last_probe_message ?? null
  };
}

function toStorageEndpointUpdateDalPayload(payload: StorageEndpointUpdatePayload): StorageEndpointDalUpdatePayload {
  const data: StorageEndpointDalUpdatePayload = {};

  if (payload.name !== undefined) data.name = payload.name;
  if (payload.description !== undefined) data.description = payload.description;
  if (payload.endpoint_type !== undefined || payload.type !== undefined) {
    data.endpoint_type = payload.endpoint_type ?? payload.type;
  }
  if (payload.protocol !== undefined) data.protocol = payload.protocol;
  if (payload.identity_source_id !== undefined) data.identity_source_id = payload.identity_source_id;
  if (payload.host !== undefined) data.host = payload.host;
  if (payload.port !== undefined) data.port = payload.port;
  if (payload.auth_type !== undefined) data.auth_type = payload.auth_type;
  if (payload.bind_dn !== undefined) data.bind_dn = payload.bind_dn;
  if (payload.bind_password_ref !== undefined) data.bind_password_ref = payload.bind_password_ref;
  if (payload.zone_id !== undefined) data.zone_id = payload.zone_id;
  if (payload.is_active !== undefined) data.is_active = payload.is_active;
  if (payload.status !== undefined) data.status = payload.status;
  if (payload.last_probe_status !== undefined) data.last_probe_status = payload.last_probe_status;
  if (payload.last_probe_at !== undefined) data.last_probe_at = payload.last_probe_at;
  if (payload.last_probe_message !== undefined) data.last_probe_message = payload.last_probe_message;

  return data;
}

export const createStorageEndpoint = (
  fetchFn: FetchLike,
  payload: StorageEndpointCreatePayload
): Promise<{ id: number }> =>
  (async () => {
    const data = await apiPostData<StorageEndpointCreateResponse>(
      fetchFn,
      '/storage-endpoints',
      toStorageEndpointCreateDalPayload(payload)
    );

    const id = Number(
      data?.id ??
        data?.storage_endpoint_id ??
        0
    );

    if (!id) {
      // Keep message generic (displayed in UI toast) but actionable.
      throw new Error('Invalid storage endpoint create response (missing id)');
    }

    return { id };
  })();

export const updateStorageEndpoint = (
  fetchFn: FetchLike,
  id: number,
  payload: StorageEndpointUpdatePayload
): Promise<{ ok: true }> =>
  apiPatchData<{ ok: true }>(fetchFn, `/storage-endpoints/${id}`, toStorageEndpointUpdateDalPayload(payload));

export const recordStorageEndpointProbeResult = (
  fetchFn: FetchLike,
  id: number,
  payload: StorageEndpointProbeResultPayload
): Promise<StorageEndpointProbeResultResponse> =>
  apiPostData<StorageEndpointProbeResultResponse>(
    fetchFn,
    `/storage-endpoints/${id}/probe-result`,
    payload
  );

export const deleteStorageEndpoint = (
  fetchFn: FetchLike,
  id: number
): Promise<void> =>
  apiDeleteData(fetchFn, `/storage-endpoints/${id}`);
