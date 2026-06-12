export type IdentitySourceInternalMeta = {
  id?: number;
  bind_dn?: string | null;
  bind_password_ref?: string | null;
  client_secret_ref?: string | null;
  last_probe_message?: string | null;
  last_snapshot_at?: string | null;
  last_snapshot_status?: string | null;
  last_snapshot_version?: number | null;
  last_snapshot_objects_count?: number | null;
  last_snapshot_users_count?: number | null;
  last_snapshot_groups_count?: number | null;
  last_snapshot_memberships_count?: number | null;
};

export type IdentitySourceCreateResult = {
  id?: number;
  source_id?: number;
  identity_source_id?: number;
  bind_password_ref?: string | null;
};

export type IdentitySnapshotMeta = {
  at: string | null;
  status: string | null;
  version: number | null;
  objects: number | null;
  users: number | null;
  groups: number | null;
  memberships: number | null;
};

export type IdentitySnapshotStorePatch = {
  lastRunAt: string | null;
  lastSnapshotStatus: string | null;
  lastSnapshotVersion: number | null;
  lastSnapshotObjectsCount: number | null;
  lastSnapshotUsersCount: number | null;
  lastSnapshotGroupsCount: number | null;
  lastSnapshotMembershipsCount: number | null;
};

export const toFiniteCount = (value: unknown): number | null => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

export const extractSnapshotMeta = (
  internal: IdentitySourceInternalMeta | null | undefined
): IdentitySnapshotMeta => ({
  at: String(internal?.last_snapshot_at ?? '').trim() || null,
  status: String(internal?.last_snapshot_status ?? '').trim() || null,
  version: toFiniteCount(internal?.last_snapshot_version),
  objects: toFiniteCount(internal?.last_snapshot_objects_count),
  users: toFiniteCount(internal?.last_snapshot_users_count),
  groups: toFiniteCount(internal?.last_snapshot_groups_count),
  memberships: toFiniteCount(internal?.last_snapshot_memberships_count)
});

export const toSnapshotStorePatch = (meta: IdentitySnapshotMeta): IdentitySnapshotStorePatch => ({
  lastRunAt: meta.at,
  lastSnapshotStatus: meta.status,
  lastSnapshotVersion: meta.version,
  lastSnapshotObjectsCount: meta.objects,
  lastSnapshotUsersCount: meta.users,
  lastSnapshotGroupsCount: meta.groups,
  lastSnapshotMembershipsCount: meta.memberships
});
