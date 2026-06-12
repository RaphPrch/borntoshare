import type { FetchLike } from './client';
import { apiDeleteData, apiGetData, apiPatchData, apiPost, apiPostData } from './client';

/*
 * =========================================================
 * Identity API
 * =========================================================
 *
 * Local accounts are managed directly for bootstrap/admin access.
 * Directory users and groups come from configured identity sources.
 *
 * =========================================================
 */

/**
 * Admin password change (LOCAL AUTH ONLY)
 *
 * - Allowed only for local admin users
 * - Not related to Identity Sources
 * - Should NOT be exposed as a core feature
 * - Can be removed entirely in V2+
 */
export type AdminChangePasswordPayload = {
  username: string;
  new_password: string;
  current_password?: string;
};

export const adminChangePassword = (
  fetchFn: FetchLike,
  payload: AdminChangePasswordPayload
) =>
  apiPost<{ detail?: string }>(fetchFn, '/auth/admin/change-password', payload);

export type UpdateIdentityPayload = {
  identity_type?: 'user' | 'group';
  display_name?: string;
  is_active?: boolean;
  application_role?: 'user' | 'platform_admin';
};

export type CreateIdentityPrincipalPayload = {
  type?: 'user' | 'group' | string;
  external_id?: string | null;
  dn?: string | null;
  username?: string | null;
  upn?: string | null;
  display_name?: string | null;
  email?: string | null;
};

export type CreateIdentityPayload = {
  identity_type: 'user' | 'group';
  auth_source: 'local' | 'ad';
  identity_source_id?: number | null;
  username?: string;
  display_name?: string;
  email?: string | null;
  temporary_password?: string;
  require_password_change?: boolean;
  application_role: 'user' | 'platform_admin';
  principal?: CreateIdentityPrincipalPayload;
};

export type IdentityOverviewItem = {
  id: string | number;
  type?: 'user' | 'group' | string;
  username?: string | null;
  display_name?: string | null;
  email?: string | null;
  auth_source?: string | null;
  external_id?: string | null;
  dn?: string | null;
  identity_source_id?: number | null;
  source_name?: string | null;
  members_count?: number | null;
  roles?: string[];
  status?: string | null;
  is_admin?: boolean | null;
  is_active?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  last_snapshot_at?: string | null;
};

export type IdentityOverviewResponse = {
  users?: IdentityOverviewItem[];
  groups?: IdentityOverviewItem[];
  items?: IdentityOverviewItem[];
};

export type IdentitySearchPayload = {
  query?: string;
  limit?: number;
  identity_source_id?: number;
  principal_type?: 'all' | 'user' | 'group' | 'ou';
};

export type ADImportRole = 'admin' | 'user';

export type ImportIdentityAdBatchPayload = {
  identity_source_id?: number;
  snapshot_source?: string;
  items: Array<
    | {
        role?: ADImportRole;
        principal?: {
          type?: 'user' | 'group' | string;
          external_id?: string | null;
          dn?: string | null;
          username?: string | null;
          display_name?: string | null;
          email?: string | null;
          status?: string | null;
          group_dns?: string[];
          group_names?: string[];
          member_dns?: string[];
        };
        query?: string;
        snapshot_source?: string;
      }
    | {
        type?: 'user' | 'group' | string;
        external_id?: string | null;
        dn?: string | null;
        username?: string | null;
        display_name?: string | null;
        email?: string | null;
      }
  >;
};

export type IdentityJobStatusResponse = {
  job_id?: string;
  status?: string;
  result?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  error?: {
    message?: string;
    [k: string]: unknown;
  } | null;
};

export const listIdentityOverview = (fetchFn: FetchLike) =>
  apiGetData<IdentityOverviewResponse>(fetchFn, '/identity');

export const updateIdentity = (
  fetchFn: FetchLike,
  identityId: string | number,
  payload: UpdateIdentityPayload
) =>
  apiPatchData(fetchFn, `/identity/${identityId}`, payload);

export const createIdentity = (
  fetchFn: FetchLike,
  payload: CreateIdentityPayload
) => apiPostData<IdentityOverviewItem>(fetchFn, '/identity', payload);

export const deleteIdentity = (
  fetchFn: FetchLike,
  identityId: string | number,
  identityType?: 'user' | 'group'
) =>
  apiDeleteData<{ id: string | number; type?: string; deleted: boolean }>(
    fetchFn,
    `/identity/${identityId}${identityType ? `?identity_type=${encodeURIComponent(identityType)}` : ''}`
  );

export type IdentityGroupMember = {
  id?: string | number;
  username?: string | null;
  display_name?: string | null;
  email?: string | null;
  status?: string | null;
  is_active?: boolean | null;
};

export const listIdentityGroupMembers = (
  fetchFn: FetchLike,
  groupId: string | number
) => apiGetData<IdentityGroupMember[]>(fetchFn, `/identity/groups/${groupId}/members`);

export const importIdentityAdBatch = (
  fetchFn: FetchLike,
  payload: ImportIdentityAdBatchPayload
) => apiPostData(fetchFn, '/identity/import/ad/batch', payload);

export const getIdentityJob = (
  fetchFn: FetchLike,
  jobId: number
) => apiGetData<IdentityJobStatusResponse>(fetchFn, `/identity/jobs/${Number(jobId)}`);
