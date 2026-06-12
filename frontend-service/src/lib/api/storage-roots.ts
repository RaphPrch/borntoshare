import { apiDeleteData, apiGetList, apiGetData, apiPatchData, apiPostData, apiPutData, type FetchLike } from "./client";

export type StorageRootContext = {
  id: number;
  storage_root_id?: number | null;
  name?: string | null;
  storage_root_name?: string | null;
  storage_root_code?: string | null;
  root_path?: string | null;
  normalized_root_path?: string | null;
  path?: string | null;
  parent_storage_root_id?: number | null;
  parent_storage_root_name?: string | null;
  parent_root_path?: string | null;
  inherit_owners?: boolean | number | null;
  inherit_tags?: boolean | number | null;
  /** @deprecated Legacy access-profile inheritance flag kept only for DAL payload compatibility. */
  inherit_access_profiles?: boolean | number | null;
  storage_endpoint_id?: number | null;
  storage_endpoint_name?: string | null;
  endpoint_name?: string | null;
  zone_name?: string | null;
  zone_code?: string | null;
  storage_zone_name?: string | null;
  guardian_count?: number | null;
  guardians_count?: number | null;
  guardians?: unknown[] | null;
  owners?: unknown[] | null;
};

export type StorageRootOwner = {
  storage_root_id: number;
  identity_id: number;
  role: StorageRootOwnerRole;
  display_name?: string | null;
  username?: string | null;
  email?: string | null;
  identity_type?: string | null;
};

export type StorageRootOwnerRole = 'guardian';

export type StorageRootOwnersUpdatePayload = {
  guardian_ids: number[];
};

export type StorageRootRoleCode = StorageRootOwnerRole;

type StorageRootRecord = {
  id?: number;
  storage_root_id?: number;
  name?: string | null;
  storage_root_name?: string | null;
  storage_root_code?: string | null;
  root_path?: string | null;
  normalized_root_path?: string | null;
  path?: string | null;
  parent_storage_root_id?: number | null;
  parent_storage_root_name?: string | null;
  parent_root_path?: string | null;
  inherit_owners?: boolean | number | null;
  inherit_tags?: boolean | number | null;
  /** @deprecated Legacy access-profile inheritance flag kept only for DAL payload compatibility. */
  inherit_access_profiles?: boolean | number | null;
  storage_endpoint_id?: number | null;
  storage_endpoint_name?: string | null;
  endpoint_name?: string | null;
  zone_name?: string | null;
  zone_code?: string | null;
  storage_zone_name?: string | null;
  guardian_count?: number | null;
  guardians_count?: number | null;
  guardians?: unknown[] | null;
  owners?: unknown[] | null;
};

type StorageRootWriteResponse = {
  id?: number;
};

export type StorageRootProbeResultPayload = {
  last_probe_status: 'success' | 'failed' | 'running' | 'unknown' | string;
  last_probe_at?: string | null;
  last_probe_message?: string | null;
  last_probe_job_id?: number | null;
  source_type?: string | null;
};

export type StorageRootProbeResultResponse = {
  storage_root_id: number;
  last_probe_status: string;
  last_probe_at: string;
  last_probe_message?: string | null;
};

type StorageRootOwnersResponse = {
  storage_root_id?: number;
  owners?: Array<Partial<StorageRootOwner>>;
};

const normalizeStorageRootOwner = (row: Partial<StorageRootOwner>): StorageRootOwner => ({
  storage_root_id: Number(row?.storage_root_id ?? 0),
  identity_id: Number(row?.identity_id ?? 0),
  role: 'guardian',
  display_name: row?.display_name ?? null,
  username: row?.username ?? null,
  email: row?.email ?? null,
  identity_type: row?.identity_type ?? null
});

/* ==================================================
 * WRITE MODELS (CRUD – MODALS / WIZARDS)
 * ================================================== */

export type StorageRootCreatePayload = {
  storage_endpoint_id: number;
  parent_storage_root_id?: number | null;
  name: string;
  root_path: string;
  inherit_owners?: boolean;
  inherit_tags?: boolean;
  /** @deprecated Still forwarded to the DAL for compatibility. New UI should not depend on this flag. */
  inherit_access_profiles?: boolean;
  status?: string;
};

export type StorageRootUpdatePayload = {
  storage_endpoint_id?: number;
  parent_storage_root_id?: number | null;
  name?: string;
  root_path?: string;
  inherit_owners?: boolean;
  inherit_tags?: boolean;
  /** @deprecated Still forwarded to the DAL for compatibility. New UI should not depend on this flag. */
  inherit_access_profiles?: boolean;
  status?: string;
  last_probe_status?: string | null;
  last_probe_at?: string | null;
  last_probe_message?: string | null;
  needs_revalidation?: boolean | null;
  revalidation_reason?: string | null;
};

type StorageRootDalCreatePayload = {
  storage_endpoint_id: number;
  parent_storage_root_id?: number;
  name: string;
  root_path: string;
  inherit_owners?: boolean;
  inherit_tags?: boolean;
  /** @deprecated DAL compatibility only. */
  inherit_access_profiles?: boolean;
  status?: string;
};

type StorageRootDalUpdatePayload = {
  storage_endpoint_id?: number;
  parent_storage_root_id?: number | null;
  name?: string;
  root_path?: string;
  inherit_owners?: boolean;
  inherit_tags?: boolean;
  /** @deprecated DAL compatibility only. */
  inherit_access_profiles?: boolean;
  status?: string;
  last_probe_status?: string | null;
  last_probe_at?: string | null;
  last_probe_message?: string | null;
  needs_revalidation?: boolean | null;
  revalidation_reason?: string | null;
};

function positiveInteger(value: number | string | null | undefined): number {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : 0;
}

function requiredTrimmed(value: string | null | undefined, label: string): string {
  const trimmed = String(value ?? '').trim();
  if (!trimmed) {
    throw new Error(`${label} is required.`);
  }
  return trimmed;
}

function optionalTrimmed(value: string | null | undefined): string | undefined {
  const trimmed = String(value ?? '').trim();
  return trimmed || undefined;
}

function toStorageRootCreateDalPayload(payload: StorageRootCreatePayload): StorageRootDalCreatePayload {
  const endpointId = positiveInteger(payload.storage_endpoint_id);
  if (!endpointId) {
    throw new Error('A storage endpoint is required to create a storage root.');
  }

  const parentId = positiveInteger(payload.parent_storage_root_id);
  const hasParent = parentId > 0;
  const data: StorageRootDalCreatePayload = {
    storage_endpoint_id: endpointId,
    name: requiredTrimmed(payload.name, 'Storage root name'),
    root_path: requiredTrimmed(payload.root_path, 'Storage root path'),
    inherit_owners: hasParent ? Boolean(payload.inherit_owners) : false,
    inherit_tags: hasParent ? Boolean(payload.inherit_tags) : false,
    inherit_access_profiles: hasParent ? Boolean(payload.inherit_access_profiles) : false,
    status: optionalTrimmed(payload.status) ?? 'active'
  };

  if (hasParent) {
    data.parent_storage_root_id = parentId;
  }

  return data;
}

function toStorageRootUpdateDalPayload(payload: StorageRootUpdatePayload): StorageRootDalUpdatePayload {
  const data: StorageRootDalUpdatePayload = {};

  if (payload.storage_endpoint_id !== undefined) {
    const endpointId = positiveInteger(payload.storage_endpoint_id);
    if (!endpointId) {
      throw new Error('A valid storage endpoint is required.');
    }
    data.storage_endpoint_id = endpointId;
  }

  if (payload.parent_storage_root_id !== undefined) {
    data.parent_storage_root_id =
      payload.parent_storage_root_id === null ? null : positiveInteger(payload.parent_storage_root_id) || null;
  }
  if (payload.name !== undefined) data.name = requiredTrimmed(payload.name, 'Storage root name');
  if (payload.root_path !== undefined) data.root_path = requiredTrimmed(payload.root_path, 'Storage root path');
  if (payload.inherit_owners !== undefined) data.inherit_owners = Boolean(payload.inherit_owners);
  if (payload.inherit_tags !== undefined) data.inherit_tags = Boolean(payload.inherit_tags);
  if (payload.inherit_access_profiles !== undefined) data.inherit_access_profiles = Boolean(payload.inherit_access_profiles);
  if (payload.status !== undefined) data.status = optionalTrimmed(payload.status);
  if (payload.last_probe_status !== undefined) data.last_probe_status = optionalTrimmed(payload.last_probe_status) ?? null;
  if (payload.last_probe_at !== undefined) data.last_probe_at = payload.last_probe_at;
  if (payload.last_probe_message !== undefined) data.last_probe_message = optionalTrimmed(payload.last_probe_message) ?? null;
  if (payload.needs_revalidation !== undefined) data.needs_revalidation = payload.needs_revalidation;
  if (payload.revalidation_reason !== undefined) data.revalidation_reason = optionalTrimmed(payload.revalidation_reason) ?? null;

  return data;
}

/**
 * Create a storage root.
 * POST /storage-roots
 */
export const createStorageRoot = (
  fetchFn: FetchLike,
  payload: StorageRootCreatePayload
): Promise<{ id: number }> =>
  (async () => {
    const data = await apiPostData<StorageRootWriteResponse>(
      fetchFn,
      "/storage-roots",
      toStorageRootCreateDalPayload(payload)
    );

    const id = Number(data?.id ?? 0);

    if (!id) {
      throw new Error('Invalid storage root create response (missing id)');
    }

    return { id };
  })();

export const updateStorageRoot = async (
  fetchFn: FetchLike,
  storageRootId: number,
  payload: StorageRootUpdatePayload
): Promise<{ id: number }> => {
  const data = await apiPatchData<StorageRootWriteResponse>(
    fetchFn,
    `/storage-roots/${storageRootId}`,
    toStorageRootUpdateDalPayload(payload)
  );
  return {
    id: Number(data?.id ?? 0)
  };
};

export const recordStorageRootProbeResult = async (
  fetchFn: FetchLike,
  storageRootId: number,
  payload: StorageRootProbeResultPayload
): Promise<StorageRootProbeResultResponse> => {
  return apiPostData<StorageRootProbeResultResponse>(
    fetchFn,
    `/storage-roots/${storageRootId}/probe-result`,
    payload
  );
};

export const deleteStorageRoot = async (
  fetchFn: FetchLike,
  storageRootId: number
): Promise<void> => {
  await apiDeleteData(fetchFn, `/storage-roots/${storageRootId}`);
};

/**
 * List storage roots context (READ-MODEL).
 * GET /storage-roots/context
 */
export const listStorageRootsContext = async (
  fetchFn: FetchLike
): Promise<StorageRootContext[]> => {
  const rows = await apiGetList<StorageRootRecord>(fetchFn, "/storage-roots/context");

  return rows.map((r) => ({
    ...r,
    id: Number(r.storage_root_id ?? r.id ?? 0),
    storage_root_id: Number(r.storage_root_id ?? r.id ?? 0),
    name: r.name ?? r.storage_root_name ?? null,
    storage_root_name: r.storage_root_name ?? r.name ?? null,
    root_path: r.root_path ?? null,
    normalized_root_path: r.normalized_root_path ?? null,
    path: r.path ?? null,
    storage_endpoint_id: r.storage_endpoint_id ?? null,
    storage_endpoint_name: r.storage_endpoint_name ?? r.endpoint_name ?? null
  }));
};

export const getStorageRootOverview = async (
  fetchFn: FetchLike,
  storageRootId: number
): Promise<Record<string, unknown>> => {
  return apiGetData<Record<string, unknown>>(fetchFn, `/storage-roots/${storageRootId}/overview`);
};

export const getStorageRootOwners = async (
  fetchFn: FetchLike,
  storageRootId: number
): Promise<StorageRootOwner[]> => {
  const data = await apiGetData<StorageRootOwnersResponse>(fetchFn, `/storage-roots/${storageRootId}/owners`);
  const owners = Array.isArray(data?.owners) ? data.owners : [];
  return owners.map(normalizeStorageRootOwner);
};

export const updateStorageRootOwners = async (
  fetchFn: FetchLike,
  storageRootId: number,
  payload: StorageRootOwnersUpdatePayload
): Promise<{ storage_root_id: number; owners: StorageRootOwner[] }> => {
  const data = await apiPutData<StorageRootOwnersResponse>(fetchFn, `/storage-roots/${storageRootId}/owners`, payload);
  const owners = Array.isArray(data?.owners) ? data.owners : [];
  return {
    storage_root_id: Number(data?.storage_root_id ?? 0),
    owners: owners.map(normalizeStorageRootOwner)
  };
};

export const assignStorageRootRole = async (
  fetchFn: FetchLike,
  storageRootId: number,
  payload: { identity_id: number; role: StorageRootRoleCode }
): Promise<{ storage_root_id: number; owners: StorageRootOwner[] }> => {
  const data = await apiPostData<StorageRootOwnersResponse>(fetchFn, `/storage-roots/${storageRootId}/roles`, payload);
  const owners = Array.isArray(data?.owners) ? data.owners : [];
  return {
    storage_root_id: Number(data?.storage_root_id ?? 0),
    owners: owners.map(normalizeStorageRootOwner)
  };
};

export const removeStorageRootRole = async (
  fetchFn: FetchLike,
  storageRootId: number,
  role: StorageRootRoleCode,
  identityId: number
): Promise<{ storage_root_id: number; owners: StorageRootOwner[] }> => {
  const data = await apiDeleteData<StorageRootOwnersResponse>(fetchFn, `/storage-roots/${storageRootId}/roles/${role}/${identityId}`);
  const owners = Array.isArray(data?.owners) ? data.owners : [];
  return {
    storage_root_id: Number(data?.storage_root_id ?? 0),
    owners: owners.map(normalizeStorageRootOwner)
  };
};
