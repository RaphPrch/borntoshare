// src/lib/api/access-profiles.ts
import {
  apiDeleteData,
  apiGetData,
  apiGetList,
  apiPostData,
  type FetchLike
} from './client';

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

export type AccessProfileMember = {
  identity_id: number | string;
  identity_kind?: string;
  display_name?: string;
  source?: string;
  added_at?: string;
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

const normalizeAccessProfile = (row: AccessProfile): AccessProfile => ({
  ...row,
  name: row?.name ?? '',
  active: row?.active ?? row?.is_active,
  is_active: row?.is_active ?? row?.active
});

export const listAccessProfiles = async (
  fetchFn: FetchLike,
  scope?: string
): Promise<AccessProfile[]> => {
  const rows = await apiGetList<AccessProfile>(fetchFn, '/access-profiles', {
    scope
  });
  return rows.map(normalizeAccessProfile);
};

export const listAccessProfileMembers = async (
  fetchFn: FetchLike,
  id: number
): Promise<AccessProfileMember[]> =>
  apiGetList<AccessProfileMember>(fetchFn, `/access-profiles/${id}/members`);

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
