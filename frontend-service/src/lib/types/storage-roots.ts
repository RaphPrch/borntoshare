import type { StorageRootOwner } from '../api/storage-roots';
import type { StorageRootTagLike } from '../utils/storage-roots';

export type StorageRootAccessLevel = 'read' | 'write';

export type StorageRootProjectedAdGroup = {
  group_name?: string;
  access_level?: string;
  profile_status?: string;
  group_external_id?: string | null;
  is_created?: boolean;
  acl_alignment?: 'present' | 'missing' | 'unknown' | string | null;
  acl_principal?: string | null;
  acl_access_level?: string | null;
  acl_raw?: string | null;
};

export type StorageRootEffectiveAccessUser = {
  row_id?: string | null;
  identity_id?: number | null;
  actor_id?: number | null;
  actor_external_id?: string | null;
  display_name?: string | null;
  username?: string | null;
  email?: string | null;
  upn?: string | null;
  identity_source_id?: number | null;
  identity_source_name?: string | null;
  directory_snapshot_id?: number | null;
  snapshot_id?: number | null;
  access_level?: StorageRootAccessLevel | string;
  source?: 'request' | 'inherited' | 'manual' | 'acl' | 'unknown' | string | null;
  access_source?: 'request' | 'inherited' | 'manual' | 'acl' | 'unknown' | string | null;
  created_at?: string | null;
  assigned_at?: string | null;
  granted_at?: string | null;
  expires_at?: string | null;
  granted_by?: string | null;
  granted_by_display_name?: string | null;
  source_entries?: number | null;
  principal?: string | null;
  principal_type?: string | null;
  acl_parent_principal?: string | null;
  is_acl_group?: boolean | null;
  members_count?: number | null;
  members?: StorageRootEffectiveAccessUser[];
  raw_acl?: string | null;
};

export type StorageRootActivityItem = {
  id?: number | string;
  action?: string;
  actor_display_name?: string | null;
  actor_name?: string | null;
  actor_username?: string | null;
  actor_email?: string | null;
  target_display?: string | null;
  target_name?: string | null;
  created_at?: string | null;
  event_time?: string | null;
  context_json?: Record<string, unknown> | null;
  metadata_json?: Record<string, unknown> | null;
  [key: string]: unknown;
};

export type StorageRootAccessProfileSummary = {
  /** @deprecated Legacy compatibility type for access-profile payloads still returned by the DAL. */
  id?: number | null;
  link_id?: number | null;
  access_profile_id?: number | null;
  access_level?: 'READ' | 'WRITE' | string;
  access_level_code?: 'READ' | 'WRITE' | string;
  code?: string | null;
  label?: string | null;
  name?: string | null;
  status?: string | null;
  members_count?: number;
  members?: number;
  profile_source?: string | null;
  source?: string | null;
  binding_status?: 'materialized' | 'inherited_candidate' | 'missing' | 'ambiguous' | string;
  is_materialized_on_root?: boolean;
  approval_ready?: boolean;
  acl_alignment?: 'present' | 'missing' | 'unknown' | string | null;
  acl_principal?: string | null;
  acl_access_level?: string | null;
  acl_raw?: string | null;
};

export type StorageRootEndpointSummary = {
  storage_endpoint_id?: number | null;
  id?: number | null;
  name?: string | null;
  storage_endpoint_name?: string | null;
  protocol?: string | null;
  storage_endpoint_type?: string | null;
  type?: string | null;
  zone_id?: number | null;
  zone_name?: string | null;
  identity_source_id?: number | null;
  identity_source_name?: string | null;
  resolved_identity_source_id?: number | null;
  resolved_identity_source_name?: string | null;
  effective_preview?: {
    effective_identity_source_id?: number | null;
    effective_identity_source_name?: string | null;
    endpoint_sub_ou_dn?: string | null;
    effective_ou_dn?: string | null;
  };
};

export type StorageRootProvisioningSummary = {
  identity_source_id?: number | null;
  identity_source_name?: string | null;
  group_ou?: string | null;
};

export type StorageRootPolicySummary = {
  resolved_identity_source_id?: number | null;
  resolved_identity_source_name?: string | null;
  resolved_group_ou?: string | null;
  endpoint_sub_ou_dn?: string | null;
  effective?: {
    endpoint_sub_ou_dn?: string | null;
    effective_ou_dn?: string | null;
  };
  effective_preview?: {
    effective_identity_source_id?: number | null;
    effective_identity_source_name?: string | null;
    effective_ou_dn?: string | null;
  };
};

export type StorageRootDetailModel = {
  storage_root_id: number;
  id?: number;
  storage_root_name?: string | null;
  name?: string | null;
  storage_root_code?: string | null;
  code?: string | null;
  root_path?: string | null;
  normalized_root_path?: string | null;
  parent_storage_root_id?: number | null;
  parent_storage_root_name?: string | null;
  parent_root_path?: string | null;
  inherit_owners?: boolean | number | null;
  inherit_tags?: boolean | number | null;
  /** @deprecated Legacy compatibility flag from the DAL. Active UI should use guardians, projected groups and effective access instead. */
  inherit_access_profiles?: boolean | number | null;
  path?: string | null;
  zone_id?: number | null;
  zone_name?: string | null;
  status?: string | null;
  provisioning_state?: string | null;
  storage_endpoint?: StorageRootEndpointSummary | null;
  effective_provisioning?: StorageRootProvisioningSummary | null;
  provisioning_policy?: StorageRootPolicySummary | null;
  owners: StorageRootOwner[];
  tags: StorageRootTagLike[];
  recent_activity: StorageRootActivityItem[];
  /** @deprecated Legacy compatibility payload. Active UI should use projected_ad_groups and effective_access instead. */
  access_profiles: StorageRootAccessProfileSummary[];
  projected_ad_groups: StorageRootProjectedAdGroup[];
  effective_access: StorageRootEffectiveAccessUser[];
  effective_access_counts: {
    read_users: number;
    write_users: number;
  };
  acl_freshness?: {
    state?: 'fresh' | 'stale' | 'not_scanned' | 'unknown' | string;
    reason?: string | null;
    scanned_at?: string | null;
    source?: string | null;
    probe_job_id?: number | string | null;
    permissions_count?: number | null;
    active_snapshot_id?: number | null;
    active_snapshot_at?: string | null;
    identity_source_id?: number | null;
  } | null;
  pending_validation_count: number;
  effective_availability?: string | null;
  needs_revalidation?: boolean | number | null;
  revalidation_reason?: string | null;
  created_at?: string | null;
  created?: string | null;
  creation_date?: string | null;
  inserted_at?: string | null;
  last_probe_at?: string | null;
  probe_last_run_at?: string | null;
  [key: string]: unknown;
};

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);
const toNullableNumber = (value: unknown): number | null => {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.trunc(n);
};

export const normalizeStorageRootDetailModel = (
  raw: unknown,
  opts?: { selectedRootId?: number | null }
): StorageRootDetailModel => {
  const source = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const selectedRootId = toNullableNumber(opts?.selectedRootId ?? null);
  const id = toNullableNumber(source.storage_root_id ?? source.id ?? selectedRootId ?? null) ?? 0;

  const counts =
    source.effective_access_counts && typeof source.effective_access_counts === 'object'
      ? (source.effective_access_counts as Record<string, unknown>)
      : {};

  return {
    ...source,
    storage_root_id: id,
    id,
    owners: toArray<StorageRootOwner>(source.owners),
    tags: toArray<StorageRootTagLike>(source.tags),
    recent_activity: toArray<StorageRootActivityItem>(source.recent_activity),
    // Keep the legacy field normalized for DAL payload compatibility, but active UI
    // should rely on projected_ad_groups and effective_access instead.
    access_profiles: toArray<StorageRootAccessProfileSummary>(source.access_profiles),
    projected_ad_groups: toArray<StorageRootProjectedAdGroup>(source.projected_ad_groups),
    effective_access: toArray<StorageRootEffectiveAccessUser>(source.effective_access),
    effective_access_counts: {
      read_users: Number(counts.read_users ?? 0) || 0,
      write_users: Number(counts.write_users ?? 0) || 0
    },
    pending_validation_count: Number(source.pending_validation_count ?? 0) || 0,
    effective_availability: String(source.effective_availability ?? '').trim().toLowerCase() || 'unknown'
  };
};
