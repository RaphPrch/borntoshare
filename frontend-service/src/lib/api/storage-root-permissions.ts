// Permissions of a storage root (core-service /storage-roots/{id}/permissions): who reaches the folder and why
import type { FetchLike } from './client';
import { apiDeleteData, apiGetData, apiPostData } from './client';

export type AccessLevel = 'read' | 'write';

export type PermissionVia =
  | { kind: 'request'; request_id: number; code: string; level: AccessLevel; group: string | null; decided_at: string | null; expires_at: string | null; requester: string | null }
  | { kind: 'group' | 'ad_only'; group: string; level: AccessLevel; nested: boolean }
  | { kind: 'outside'; group: string; level: AccessLevel | null; accepted: boolean };

export type PermissionPerson = {
  key: string;
  username: string | null;
  name: string;
  dn: string | null;
  level: AccessLevel | null;
  via: PermissionVia[];
  expires_at: string | null;
  revocable_request_ids: number[];
  warnings: Array<'missing_in_group' | 'awaiting_sync'>;
};

export type PermissionGroup = {
  name: string;
  level: AccessLevel;
  dn: string | null;
  ace: 'ok' | 'missing' | 'mismatch' | 'unknown';
  rights_label: string | null;
  inherited_scope: boolean;
  members_count: number;
};

export type AclEntry = {
  principal: string;
  name: string;
  rights: 'full' | 'modify' | 'read' | 'special' | 'deny';
  rights_label: string;
  level: AccessLevel | null;
  inherited_scope: boolean;
  raw: string;
  kind: 'system' | 'service' | 'outside' | 'broad';
  accepted?: boolean;
  accepted_by?: string | null;
  members_count?: number;
};

export type StorageRootPermissionsData = {
  propagation?: { state: 'running' | 'failed' | 'done'; message?: string | null; at?: string | null } | null;
  storage_root_id: number;
  root_path: string | null;
  acl_scanned_at: string | null;
  acl_entries: number;
  /** NTFS inheritance of the folder from its parent (CONTROL flags of the last ACL read) */
  inheritance: { known: boolean; broken: boolean; inherited_entries: number };
  snapshot_at: string | null;
  status: 'ok' | 'gap' | 'missing_ace' | 'never_scanned';
  summary: { people: number; read: number; write: number; groups: number; groups_ok: number; expiring_30d: number; gaps: number; accepted_gaps: number };
  people: PermissionPerson[];
  groups: PermissionGroup[];
  system: AclEntry[];
  gaps: AclEntry[];
};

export type ExplainStep =
  | ({ kind: 'request'; approver: string | null } & Extract<PermissionVia, { kind: 'request' }>)
  | { kind: 'membership'; group: string; managed: boolean; outside_request: boolean; nested: boolean; ou: string | null }
  | { kind: 'ace'; group: string; state: PermissionGroup['ace']; rights_label: string | null; inherited_scope: boolean; level: AccessLevel | null };

export type AccessExplanation =
  | { found: true; person: PermissionPerson; steps: ExplainStep[]; other_roots: Array<{ storage_root_id: number; name: string; level: AccessLevel }>; acl_scanned_at: string | null; snapshot_at: string | null }
  | { found: false; username: string; known_in_directory: boolean; display_name: string | null; acl_scanned_at: string | null; snapshot_at: string | null };

export type AccessNotFound = Extract<AccessExplanation, { found: false }>;
export const notFound = (value: AccessExplanation | null): AccessNotFound | null => (value && !value.found ? (value as AccessNotFound) : null);

export const getStorageRootPermissions = (fetchFn: FetchLike, rootId: number) =>
  apiGetData<StorageRootPermissionsData>(fetchFn, `/storage-roots/${rootId}/permissions`);

export const explainStorageRootAccess = (fetchFn: FetchLike, rootId: number, username: string) =>
  apiGetData<AccessExplanation>(fetchFn, `/storage-roots/${rootId}/permissions/explain`, { username });

export const acceptAclGap = (fetchFn: FetchLike, rootId: number, principal: string, note?: string) =>
  apiPostData(fetchFn, `/storage-roots/${rootId}/permissions/exceptions`, { principal, note: note ?? null });

export const reopenAclGap = (fetchFn: FetchLike, rootId: number, principal: string) =>
  apiDeleteData(fetchFn, `/storage-roots/${rootId}/permissions/exceptions?principal=${encodeURIComponent(principal)}`);

export const extendAccess = (fetchFn: FetchLike, accessRequestId: number, days = 30) =>
  apiPostData<{ id: number; expires_at: string | null }>(fetchFn, `/access-requests/${accessRequestId}/extend`, { days });

/** Break (inherited entries kept as explicit ones) or restore the inheritance of the folder, by the worker */
export const setFolderInheritance = (fetchFn: FetchLike, rootId: number, mode: 'break' | 'restore') =>
  apiPostData<{ storage_root_id: number; inheritance_broken: boolean }>(fetchFn, `/storage-roots/${rootId}/inheritance`, { mode });

/** Delete the folder and its content on the file server, then the storage root */
export const deleteStorageRootFolder = (fetchFn: FetchLike, rootId: number, confirmName: string) =>
  apiPostData(fetchFn, `/storage-roots/${rootId}/delete-folder`, { confirm_name: confirmName });

export type PersonSearchResult = { username: string; name: string; dn: string | null; identity_source_id: number | null; roots: Array<{ storage_root_id: number; name: string; level: AccessLevel }> };

export const searchPeople = (fetchFn: FetchLike, query: string) =>
  apiGetData<PersonSearchResult[]>(fetchFn, '/storage-roots/people/search', { q: query });

/** Create a sub-folder on the file server, and its storage root when `register` */
export const createSubfolder = (fetchFn: FetchLike, rootId: number, name: string, register = true) =>
  apiPostData<{ path: string; storage_root_id: number | null }>(fetchFn, `/storage-roots/${rootId}/subfolders`, { name, register });

/** Put back the entries of the BornToShare groups on the folder and its content */
export const repairStorageRootAcl = (fetchFn: FetchLike, rootId: number) =>
  apiPostData<{ groups: string[] }>(fetchFn, `/storage-roots/${rootId}/permissions/repair`, undefined, { timeoutMs: 180_000 });
