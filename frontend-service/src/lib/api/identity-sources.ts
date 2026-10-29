import type { FetchLike } from './client';
import {
  apiDeleteData,
  apiGetData,
  apiGetList,
  apiPatchData,
  apiPostData
} from './client';

type IdentityBrowseStatus = 'up_to_date' | 'needs_refresh';

type IdentityBrowseItem = {
  username?: string | null;
  display_name?: string | null;
  upn?: string | null;
  ou?: string | null;
  group_count?: number;
  enabled?: boolean;
  status?: IdentityBrowseStatus;
};

type IdentityBrowseResponse = {
  identity_source_id: number;
  count: number;
  items: IdentityBrowseItem[];
  proposed_imports?: IdentityBrowseItem[];
};

/** Purposes that can use their own service account instead of the account of the source */
export type ServiceAccountPurpose = 'snapshot' | 'auth' | 'provisioning';

/** Write: an empty bind_dn (or null) removes the dedicated account; a missing ref keeps the stored password */
export type ServiceAccountInput = { bind_dn: string | null; bind_password_ref?: string | null } | null;

/** Read: the reference to the password is never sent to the browser */
export type ServiceAccountPublic = { bind_dn: string; has_password: boolean };

export type IdentitySourcePayload = {
  type: 'ad';
  name: string;
  protocol?: 'ldap' | 'ldaps';
  host?: string | null;
  port?: number | null;
  base_dn?: string | null;
  domain_name?: string | null;
  bind_dn?: string | null;

  /** Secret reference stored by backend secret management */
  bind_password_ref?: string | null;
  service_accounts?: Partial<Record<ServiceAccountPurpose, ServiceAccountInput>>;

  issuer_url?: string | null;
  client_id?: string | null;

  /** Secret reference stored by backend secret management */
  client_secret_ref?: string | null;

  capabilities?: {
    auth?: boolean;
    import_groups?: boolean;
    snapshot_enabled?: boolean;
    /** Create AD groups and change their members (capsule-runner) */
    provisioning?: boolean;
    auth_mode?: 'ntlm' | 'kerberos';
  };

  auth_enabled?: boolean;
  auth_priority?: number;

  is_active?: boolean;
};

type IdentitySourceApiWritePayload = {
  type: 'ad';
  name: string;
  issuer_url?: string | null;
  protocol?: 'ldap' | 'ldaps';
  host?: string | null;
  port?: number | null;
  base_dn?: string | null;
  domain_name?: string | null;
  bind_dn?: string | null;
  bind_password_ref?: string | null;
  service_accounts?: IdentitySourcePayload['service_accounts'];
  capabilities?: IdentitySourcePayload['capabilities'];
  auth_enabled?: boolean;
  auth_priority?: number;
  is_active?: boolean;
};

type IdentitySourceApiUpdatePayload = Partial<Omit<IdentitySourceApiWritePayload, 'type'>>;

export type IdentitySourceListItem = {
  id: number;
  type?: string | null;
  name?: string | null;
  protocol?: 'ldap' | 'ldaps' | string | null;
  host?: string | null;
  port?: number | null;
  base_dn?: string | null;
  domain_name?: string | null;
  bind_dn?: string | null;
  service_accounts?: Partial<Record<ServiceAccountPurpose, ServiceAccountPublic>>;
  is_active?: boolean;
  last_snapshot_at?: string | null;
  last_snapshot_status?: string | null;
  snapshot_running?: boolean;
  last_snapshot_version?: number | null;
  last_snapshot_objects_count?: number | null;
  last_snapshot_users_count?: number | null;
  last_snapshot_groups_count?: number | null;
  last_snapshot_memberships_count?: number | null;
  capabilities?: {
    auth?: boolean;
    import_groups?: boolean;
    snapshot_enabled?: boolean;
    /** Create AD groups and change their members (capsule-runner) */
    provisioning?: boolean;
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

function toIdentitySourceCreateApiPayload(payload: IdentitySourcePayload): IdentitySourceApiWritePayload {
  return {
    type: 'ad',
    name: payload.name,
    issuer_url: toNullableTrimmedString(payload.issuer_url),
    protocol: normalizeAdProtocol(payload.protocol),
    host: toNullableTrimmedString(payload.host),
    port: normalizePort(payload.port),
    base_dn: toNullableTrimmedString(payload.base_dn),
    domain_name: toNullableTrimmedString(payload.domain_name),
    bind_dn: toNullableTrimmedString(payload.bind_dn),
    bind_password_ref: toNullableTrimmedString(payload.bind_password_ref),
    service_accounts: payload.service_accounts,
    capabilities: payload.capabilities,
    auth_enabled: payload.auth_enabled ?? false,
    auth_priority: payload.auth_priority ?? 100,
    is_active: payload.is_active ?? true
  };
}

function toIdentitySourceUpdateApiPayload(payload: Partial<IdentitySourcePayload>): IdentitySourceApiUpdatePayload {
  const data: IdentitySourceApiUpdatePayload = {};

  if (payload.name !== undefined) data.name = payload.name;
  if (payload.issuer_url !== undefined) data.issuer_url = toNullableTrimmedString(payload.issuer_url);
  if (payload.protocol !== undefined) data.protocol = normalizeAdProtocol(payload.protocol);
  if (payload.host !== undefined) data.host = toNullableTrimmedString(payload.host);
  if (payload.port !== undefined) data.port = normalizePort(payload.port);
  if (payload.base_dn !== undefined) data.base_dn = toNullableTrimmedString(payload.base_dn);
  if (payload.domain_name !== undefined) data.domain_name = toNullableTrimmedString(payload.domain_name);
  if (payload.service_accounts !== undefined) data.service_accounts = payload.service_accounts;
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
) => apiPostData(fetchFn, '/identity-sources', toIdentitySourceCreateApiPayload(payload));

export const updateIdentitySource = (
  fetchFn: FetchLike,
  sourceId: number,
  payload: Partial<IdentitySourcePayload>
) => apiPatchData(fetchFn, `/identity-sources/${sourceId}`, toIdentitySourceUpdateApiPayload(payload));

export const deleteIdentitySource = (fetchFn: FetchLike, sourceId: number) =>
  apiDeleteData(fetchFn, `/identity-sources/${sourceId}`);

export const getIdentitySourceInternal = (fetchFn: FetchLike, sourceId: number) =>
  apiGetData(fetchFn, `/identity-sources/${sourceId}/internal`);

type IdentitySnapshotRunResponse = {
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

/** Sample of the directory objects of a source (same search as the beneficiary picker) */
export const browseIdentitySource = (
  fetchFn: FetchLike,
  sourceId: number,
  params?: { q?: string; limit?: number; principal_type?: 'all' | 'user' | 'group' | 'ou' }
) =>
  apiPostData<IdentityBrowseResponse>(fetchFn, '/identity/search', {
    identity_source_id: Number(sourceId),
    query: String(params?.q ?? '').trim(),
    principal_type: params?.principal_type ?? 'all',
    search_scope: 'subtree',
    limit: Number(params?.limit ?? 50)
  });
