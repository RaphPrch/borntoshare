// src/lib/api/access-profiles.ts
import {
  apiDeleteData,
  apiGetData,
  apiGetList,
  apiPostData,
  type FetchLike
} from './client';
import type { AccessProfileConsole } from '../types/access-profile-console';
export type ListResponse<T> = {
  items: T[];
  total?: number;
  offset?: number;
  limit?: number;
};

export type AccessProfile = {
  id?: number | string;
  code?: string;
  name?: string;
  description?: string | null;
  is_active?: boolean;
  permission?: 'READ' | 'WRITE' | string;
  storage_root_id?: number;
  access_level_code?: 'READ' | 'WRITE' | string;
  group_name?: string | null;
  acl_alignment?: 'present' | 'missing' | 'unknown' | string | null;
  acl_principal?: string | null;
  acl_access_level?: string | null;
  acl_raw?: string | null;
  source?: 'INHERITED' | 'LOCAL' | string;
  members_count?: number;
  status?: string;
  updated_at?: string | null;
  last_error_message?: string | null;
  correlation_id?: string | null;
  locked?: boolean;
  active?: boolean;
  used_in_roots_count?: number;
  created_at?: string;
};

export type AccessProfileWrite = {
  code?: string;
  name?: string;
  description?: string | null;
  permission?: 'READ' | 'WRITE' | string;
  storage_root_id?: number;
  access_level_code?: 'READ' | 'WRITE' | string;
  active?: boolean;
};

export type AccessProfileMember = {
  identity_id: number | string;
  identity_kind?: string;
  display_name?: string;
  source?: string;
  added_at?: string;
};

export type AccessProfileActivityItem = {
  id?: number | string;
  action?: string;
  outcome?: string;
  severity?: string;
  actor_display?: string;
  actor_display_name?: string;
  target_display?: string;
  context_json?: Record<string, unknown> | null;
  metadata_json?: Record<string, unknown> | null;
  created_at?: string;
  event_time?: string;
  [k: string]: unknown;
};

export type StorageRootAccessProfileMapping = {
  access_profile_id: number;
  group_name: string;
  [k: string]: unknown;
};

export type StorageRootAccessProfilesState = {
  storage_root_id: number;
  attached_profiles: AccessProfile[];
};

type StorageRootAccessProfilesPayload = {
  storage_root_id?: number | string;
  attached_profiles?: AccessProfile[];
  items?: AccessProfile[];
};

const extractAttachedProfileRows = (
  payload: StorageRootAccessProfilesPayload | AccessProfile[] | null | undefined
): AccessProfile[] => {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== 'object') return [];
  if (Array.isArray(payload.attached_profiles)) return payload.attached_profiles;
  if (Array.isArray(payload.items)) return payload.items;
  return [];
};

type StorageRootAccessProfileReadinessPayload = {
  storage_root_id?: number | string;
  ready?: boolean;
  identity_source_kind?: string | null;
  identity_source_id?: number | string | null;
  zone_id?: number | string | null;
  write_enabled?: boolean;
  has_secret_ref?: boolean;
  secret_ref?: string | null;
  effective_group_ou_dn?: string | null;
  missing_requirements?: Array<{
    code?: string;
    message?: string;
  }>;
};

const normalizeAccessProfile = (row: AccessProfile): AccessProfile => ({
  ...row,
  name: row?.name ?? '',
  active: row?.active ?? row?.is_active,
  is_active: row?.is_active ?? row?.active
});

export type StorageRootAccessProfileReadinessMissingRequirement = {
  code: string;
  message: string;
};

export type StorageRootAccessProfileReadiness = {
  storage_root_id: number;
  ready: boolean;
  identity_source_kind?: string | null;
  identity_source_id?: number | null;
  zone_id?: number | null;
  write_enabled?: boolean;
  has_secret_ref?: boolean;
  secret_ref?: string | null;
  effective_group_ou_dn?: string | null;
  missing_requirements?: StorageRootAccessProfileReadinessMissingRequirement[];
};

export const listAccessProfiles = async (
  fetchFn: FetchLike,
  scope?: string
): Promise<AccessProfile[]> => {
  const rows = await apiGetList<AccessProfile>(fetchFn, '/access-profiles', {
    scope
  });
  return rows.map(normalizeAccessProfile);
};

export const getAccessProfile = async (fetchFn: FetchLike, id: number) =>
  apiGetData<AccessProfile>(fetchFn, `/access-profiles/${id}`);

export const listAccessProfileMembers = async (
  fetchFn: FetchLike,
  id: number
): Promise<AccessProfileMember[]> =>
  apiGetList<AccessProfileMember>(fetchFn, `/access-profiles/${id}/members`);

export const listAccessProfileActivity = async (
  fetchFn: FetchLike,
  id: number
): Promise<AccessProfileActivityItem[]> =>
  apiGetList<AccessProfileActivityItem>(fetchFn, `/access-profiles/${id}/activity`);

export const createStorageRootAccessProfile = async (
  fetchFn: FetchLike,
  storageRootId: number,
  accessLevel: 'READ' | 'WRITE' | string
) =>
  apiPostData<AccessProfile>(fetchFn, `/storage-roots/${storageRootId}/access-profiles`, {
    access_level: String(accessLevel || 'READ').trim().toUpperCase()
  });

export const listStorageRootAccessProfileMappings = async (
  fetchFn: FetchLike,
  storageRootId: string
): Promise<StorageRootAccessProfilesState> => {
  const data = await apiGetData<StorageRootAccessProfilesPayload>(
    fetchFn,
    `/storage-roots/${storageRootId}/access-profiles`
  );
  const attachedRows = extractAttachedProfileRows(data);

  return {
    storage_root_id: Number(data?.storage_root_id ?? storageRootId),
    attached_profiles: attachedRows.map((row) => ({
      ...normalizeAccessProfile(row),
      id: Number(row?.id ?? 0),
      status: String(row?.status ?? 'PENDING'),
      updated_at: row?.updated_at ?? null,
      last_error_message: row?.last_error_message ?? null,
      correlation_id: row?.correlation_id ?? null,
      active: row?.active ?? row?.is_active,
      is_active: row?.is_active ?? row?.active
    }))
  };
};

export const upsertStorageRootAccessProfileMapping = async (
  fetchFn: FetchLike,
  storageRootId: string,
  input:
    | {
        access_level?: 'READ' | 'WRITE' | string;
      }
): Promise<StorageRootAccessProfilesState> => {
  const payload = {
    access_level: String(input.access_level || '').trim().toUpperCase()
  };

  if (payload.access_level !== 'READ' && payload.access_level !== 'WRITE') {
    throw new Error('access_level must be READ or WRITE');
  }

  const data = await apiPostData<StorageRootAccessProfilesPayload>(
    fetchFn,
    `/storage-roots/${storageRootId}/access-profiles`,
    payload
  );
  return {
    storage_root_id: Number(data?.storage_root_id ?? storageRootId),
    attached_profiles: extractAttachedProfileRows(data).map(normalizeAccessProfile)
  };
};

export const getStorageRootAccessProfileReadiness = async (
  fetchFn: FetchLike,
  storageRootId: string
): Promise<StorageRootAccessProfileReadiness> => {
  const data = await apiGetData<StorageRootAccessProfileReadinessPayload>(
    fetchFn,
    `/storage-roots/${storageRootId}/access-profiles/readiness`
  );
  return {
    storage_root_id: Number(data?.storage_root_id ?? storageRootId),
    ready: Boolean(data?.ready),
    identity_source_kind: data?.identity_source_kind ?? null,
    identity_source_id: Number.isFinite(Number(data?.identity_source_id)) ? Number(data?.identity_source_id) : null,
    zone_id: Number.isFinite(Number(data?.zone_id)) ? Number(data?.zone_id) : null,
    write_enabled: Boolean(data?.write_enabled),
    has_secret_ref: Boolean(data?.has_secret_ref),
    secret_ref: data?.secret_ref ?? null,
    effective_group_ou_dn: data?.effective_group_ou_dn ?? null,
    missing_requirements: Array.isArray(data?.missing_requirements)
      ? data.missing_requirements
          .map((row) => ({
            code: String(row?.code ?? '').trim(),
            message: String(row?.message ?? '').trim()
          }))
          .filter((row: StorageRootAccessProfileReadinessMissingRequirement) => row.code || row.message)
      : []
  };
};

export const detachStorageRootAccessProfileMapping = async (
  fetchFn: FetchLike,
  storageRootId: string,
  accessProfileId: number
): Promise<StorageRootAccessProfilesState> => {
  const data = await apiDeleteData<StorageRootAccessProfilesPayload>(
    fetchFn,
    `/storage-roots/${storageRootId}/access-profiles/${accessProfileId}`
  );
  return {
    storage_root_id: Number(data?.storage_root_id ?? storageRootId),
    attached_profiles: extractAttachedProfileRows(data).map(normalizeAccessProfile)
  };
};

export async function getAccessProfileConsole(
  id: number,
  fetcher: FetchLike = fetch
): Promise<AccessProfileConsole> {
  return apiGetData<AccessProfileConsole>(fetcher, `/access-profiles/${id}/console`);
}
