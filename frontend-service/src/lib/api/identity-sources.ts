import type { FetchLike } from './client';
import {
  apiDeleteData,
  apiGetData,
  apiGetList,
  apiPatchData,
  apiPostData
} from './client';
import { runProbeJob, getProbeJob } from './probes';

export type IdentityBrowseStatus = 'up_to_date' | 'needs_refresh';

export type IdentityBrowseItem = {
  username?: string | null;
  display_name?: string | null;
  upn?: string | null;
  ou?: string | null;
  group_count?: number;
  enabled?: boolean;
  status?: IdentityBrowseStatus;
};

export type IdentityBrowseResponse = {
  identity_source_id: number;
  count: number;
  items: IdentityBrowseItem[];
  proposed_imports?: IdentityBrowseItem[];
};

export type IdentitySourcePayload = {
  type: 'ad';
  name: string;
  protocol?: 'ldap' | 'ldaps';
  host?: string | null;
  port?: number | null;
  base_dn?: string | null;
  bind_dn?: string | null;

  /** Secret reference stored by backend secret management */
  bind_password_ref?: string | null;

  issuer_url?: string | null;
  client_id?: string | null;

  /** Secret reference stored by backend secret management */
  client_secret_ref?: string | null;

  capabilities?: {
    auth?: boolean;
    import_groups?: boolean;
    snapshot_enabled?: boolean;
    auth_mode?: 'ntlm' | 'kerberos';
  };

  auth_enabled?: boolean;
  auth_priority?: number;

  is_active?: boolean;
};

type IdentitySourceDalWritePayload = {
  type: 'ad';
  name: string;
  issuer_url?: string | null;
  protocol?: 'ldap' | 'ldaps';
  host?: string | null;
  port?: number | null;
  base_dn?: string | null;
  bind_dn?: string | null;
  bind_password_ref?: string | null;
  capabilities?: IdentitySourcePayload['capabilities'];
  auth_enabled?: boolean;
  auth_priority?: number;
  is_active?: boolean;
};

type IdentitySourceDalUpdatePayload = Partial<Omit<IdentitySourceDalWritePayload, 'type'>>;

export type IdentitySourceListItem = {
  id: number;
  type?: string | null;
  name?: string | null;
  protocol?: 'ldap' | 'ldaps' | string | null;
  host?: string | null;
  port?: number | null;
  base_dn?: string | null;
  is_active?: boolean;
  last_snapshot_at?: string | null;
  last_snapshot_status?: string | null;
  last_snapshot_version?: number | null;
  last_snapshot_objects_count?: number | null;
  last_snapshot_users_count?: number | null;
  last_snapshot_groups_count?: number | null;
  last_snapshot_memberships_count?: number | null;
  capabilities?: {
    auth?: boolean;
    import_groups?: boolean;
    snapshot_enabled?: boolean;
    auth_mode?: 'ntlm' | 'kerberos';
  };
};

export const listIdentitySources = (fetchFn: FetchLike) =>
  apiGetList<IdentitySourceListItem>(fetchFn, '/identity-sources');

function normalizeAdProtocol(value: IdentitySourcePayload['protocol']): 'ldap' | 'ldaps' {
  return value === 'ldap' ? 'ldap' : 'ldaps';
}

function normalizePort(value: number | null | undefined): number | null {
  if (value === null || value === undefined || value === 0) return null;
  const port = Number(value);
  return Number.isInteger(port) && port > 0 ? port : null;
}

function toNullableTrimmedString(value: string | null | undefined): string | null {
  const trimmed = String(value ?? '').trim();
  return trimmed ? trimmed : null;
}

function toIdentitySourceCreateDalPayload(payload: IdentitySourcePayload): IdentitySourceDalWritePayload {
  return {
    type: 'ad',
    name: payload.name,
    issuer_url: toNullableTrimmedString(payload.issuer_url),
    protocol: normalizeAdProtocol(payload.protocol),
    host: toNullableTrimmedString(payload.host),
    port: normalizePort(payload.port),
    base_dn: toNullableTrimmedString(payload.base_dn),
    bind_dn: toNullableTrimmedString(payload.bind_dn),
    bind_password_ref: toNullableTrimmedString(payload.bind_password_ref),
    capabilities: payload.capabilities,
    auth_enabled: payload.auth_enabled ?? false,
    auth_priority: payload.auth_priority ?? 100,
    is_active: payload.is_active ?? true
  };
}

function toIdentitySourceUpdateDalPayload(payload: Partial<IdentitySourcePayload>): IdentitySourceDalUpdatePayload {
  const data: IdentitySourceDalUpdatePayload = {};

  if (payload.name !== undefined) data.name = payload.name;
  if (payload.issuer_url !== undefined) data.issuer_url = toNullableTrimmedString(payload.issuer_url);
  if (payload.protocol !== undefined) data.protocol = normalizeAdProtocol(payload.protocol);
  if (payload.host !== undefined) data.host = toNullableTrimmedString(payload.host);
  if (payload.port !== undefined) data.port = normalizePort(payload.port);
  if (payload.base_dn !== undefined) data.base_dn = toNullableTrimmedString(payload.base_dn);
  if (payload.bind_dn !== undefined) data.bind_dn = toNullableTrimmedString(payload.bind_dn);
  if (payload.bind_password_ref !== undefined) data.bind_password_ref = toNullableTrimmedString(payload.bind_password_ref);
  if (payload.capabilities !== undefined) data.capabilities = payload.capabilities;
  if (payload.auth_enabled !== undefined) data.auth_enabled = payload.auth_enabled;
  if (payload.auth_priority !== undefined) data.auth_priority = payload.auth_priority;
  if (payload.is_active !== undefined) data.is_active = payload.is_active;

  return data;
}

export const createIdentitySource = (
  fetchFn: FetchLike,
  payload: IdentitySourcePayload
) => apiPostData(fetchFn, '/identity-sources', toIdentitySourceCreateDalPayload(payload));

export { runProbeJob, getProbeJob };

export const updateIdentitySource = (
  fetchFn: FetchLike,
  sourceId: number,
  payload: Partial<IdentitySourcePayload>
) => apiPatchData(fetchFn, `/identity-sources/${sourceId}`, toIdentitySourceUpdateDalPayload(payload));

export const deleteIdentitySource = (fetchFn: FetchLike, sourceId: number) =>
  apiDeleteData(fetchFn, `/identity-sources/${sourceId}`);

export const getIdentitySourceInternal = (fetchFn: FetchLike, sourceId: number) =>
  apiGetData(fetchFn, `/identity-sources/${sourceId}/internal`);

export type IdentitySnapshotRunResponse = {
  job_id?: number;
  snapshot_id?: number;
  status?: string;
  source_id?: number;
  mode?: string;
};

export const runIdentitySnapshot = (
  fetchFn: FetchLike,
  sourceId: number,
  mode: 'auto' | 'full' | 'dirsync' | 'usn' | 'whenchanged' = 'auto'
) =>
  apiPostData<IdentitySnapshotRunResponse>(
    fetchFn,
    '/identity/snapshots/run',
    {
      identity_source_id: Number(sourceId),
      mode,
      force_full: mode === 'full'
    },
    { timeoutMs: 10000 }
  );

export const browseIdentitySource = (
  fetchFn: FetchLike,
  sourceId: number,
  params?: { q?: string; limit?: number; principal_type?: 'all' | 'user' | 'group' | 'ou' }
) => apiGetData<IdentityBrowseResponse>(fetchFn, `/identity-sources/${sourceId}/browse`, params);

export const listIdentitySourceGroups = (
  fetchFn: FetchLike,
  sourceId: number,
  query: string
) => apiGetList<any>(fetchFn, `/identity-sources/${sourceId}/groups`, { q: query });

export const importIdentitySourceGroup = (
  fetchFn: FetchLike,
  sourceId: number,
  dn: string
) => apiGetData(fetchFn, `/identity-sources/${sourceId}/groups/import`, { dn });
