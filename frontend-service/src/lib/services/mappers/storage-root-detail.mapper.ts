import type { StorageRootDetailModel } from '$lib/types/storage-roots';
import type { StorageRootRow, StorageRootTagLike } from '$lib/utils/storage-roots';

export type StorageRootAccessModelRow = {
  level: 'read' | 'write';
  code: string;
  label: string;
  icon: string;
  tone: 'read' | 'write';
  users: number;
  adGroup: string;
  adGroupTone: 'success' | 'pending' | 'warning';
  groupName?: string | null;
  aclAlignment?: string | null;
  aclPrincipal?: string | null;
};

export type RootAvailability =
  | 'reachable'
  | 'checking'
  | 'unreachable'
  | 'unknown'
  | 'blocked_by_endpoint'
  | 'needs_revalidation'
  | 'root_unreachable'
  | 'needs_root_probe'
  | 'not_provisioned';
export type RootTone = 'healthy' | 'warning' | 'error';

export const storageRootIdOf = (row: unknown): number => {
  const source = (row && typeof row === 'object' ? row : {}) as Record<string, unknown>;
  return Number(source.storage_root_id ?? source.id ?? 0);
};

const parseUtcLikeDate = (value: unknown): Date | null => {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(raw)
    ? raw.replace(' ', 'T') + 'Z'
    : /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(raw)
      ? raw + 'Z'
      : raw;
  const parsed = new Date(normalized);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
};

export const formatDateTimeLabel = (value: unknown): string => {
  if (!value) return '—';
  const d = parseUtcLikeDate(value);
  if (!d) return '—';
  return d.toLocaleString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
};

export const storageRootEndpointLabel = (
  row: StorageRootRow | null,
  endpoint: Record<string, unknown> | null | undefined
): string => {
  const ep = ((endpoint?.storage_endpoint as Record<string, unknown> | undefined) ?? endpoint) as Record<string, unknown> | null | undefined;
  return String(
    ep?.storage_endpoint_name ??
    ep?.label ??
    ep?.name ??
    ep?.display_name ??
    ep?.host ??
    ep?.hostname ??
    row?.storage_endpoint_name ??
    '—'
  );
};

export const isSelectedStorageRootRow = (
  row: unknown,
  selectedStorageRootId: number | null | undefined,
  overview: StorageRootDetailModel | null
): boolean => {
  const rowId = storageRootIdOf(row);
  if (!Number.isFinite(rowId) || rowId <= 0) return false;

  const selectedId = Number(selectedStorageRootId ?? 0);
  if (Number.isFinite(selectedId) && selectedId > 0) {
    return rowId === selectedId;
  }

  const overviewId = Number(overview?.storage_root_id ?? overview?.id ?? 0);
  return Number.isFinite(overviewId) && overviewId > 0 && rowId === overviewId;
};

export const normalizeStorageRootAvailability = (value: unknown): RootAvailability => {
  const key = String(value ?? '').trim().toLowerCase();
  if (key === 'reachable') return 'reachable';
  if (key === 'checking') return 'checking';
  if (key === 'unreachable') return 'unreachable';
  if (key === 'blocked_by_endpoint') return 'blocked_by_endpoint';
  if (key === 'needs_revalidation') return 'needs_revalidation';
  if (key === 'root_unreachable') return 'root_unreachable';
  if (key === 'needs_root_probe') return 'needs_root_probe';
  if (key === 'not_provisioned') return 'not_provisioned';
  return 'unknown';
};

export const storageRootToneFromAvailability = (availability: RootAvailability): RootTone => {
  if (availability === 'reachable') return 'healthy';
  if (availability === 'unreachable' || availability === 'blocked_by_endpoint' || availability === 'root_unreachable') return 'error';
  return 'warning';
};

export const storageRootPendingCount = (
  row: Record<string, unknown>,
  selectedStorageRootId: number | null | undefined,
  overview: StorageRootDetailModel | null
): number => {
  const id = storageRootIdOf(row);
  if (id > 0 && id === Number(selectedStorageRootId ?? 0)) {
    return Number(overview?.pending_validation_count ?? row?.pending_validation_count ?? 0);
  }
  return Number(row?.pending_validation_count ?? row?.pending_requests ?? row?.requests_pending ?? 0);
};

export const effectiveAccessUsers = (overview: StorageRootDetailModel | null): Array<Record<string, unknown>> =>
  Array.isArray(overview?.effective_access) ? (overview.effective_access as Array<Record<string, unknown>>) : [];

export const effectiveAccessUsersByLevel = (
  overview: StorageRootDetailModel | null,
  level: 'read' | 'write'
): Array<Record<string, unknown>> =>
  effectiveAccessUsers(overview).filter((user) => String(user?.access_level ?? '').toLowerCase() === level);

const userIdentityKey = (row: Record<string, unknown>): string => {
  const id = Number(row?.identity_id ?? row?.actor_id ?? 0);
  if (Number.isFinite(id) && id > 0) return `id:${Math.trunc(id)}`;
  const upn = String(row?.upn ?? '').trim().toLowerCase();
  if (upn) return `upn:${upn}`;
  const username = String(row?.username ?? '').trim().toLowerCase();
  if (username) return `username:${username}`;
  const email = String(row?.email ?? '').trim().toLowerCase();
  if (email) return `email:${email}`;
  const principal = String(row?.principal ?? '').trim().toLowerCase();
  return principal ? `principal:${principal}` : '';
};

const isGroupLikeEffectiveRow = (row: Record<string, unknown>): boolean => {
  const principalType = String(row?.principal_type ?? '').trim().toLowerCase();
  return Boolean(row?.is_acl_group) || principalType.includes('group') || Array.isArray(row?.members);
};

export const effectiveAccessCount = (overview: StorageRootDetailModel | null, level: 'read' | 'write'): number => {
  const seen = new Set<string>();

  for (const row of effectiveAccessUsersByLevel(overview, level)) {
    const rec = row as Record<string, unknown>;
    const members = Array.isArray(rec.members) ? rec.members as Record<string, unknown>[] : [];

    if (members.length > 0) {
      for (const member of members) {
        const key = userIdentityKey(member);
        if (key) seen.add(key);
      }
      continue;
    }

    if (isGroupLikeEffectiveRow(rec)) continue;
    const key = userIdentityKey(rec);
    if (key) seen.add(key);
  }

  return seen.size;
};

type ProjectedAdGroup = {
  group_name?: string;
  access_level?: string;
  profile_status?: string;
  error_message?: string | null;
  correlation_id?: string | null;
  group_external_id?: string | null;
  is_created?: boolean;
  acl_alignment?: string | null;
  acl_principal?: string | null;
};

export const projectedAdGroupsRows = (overview: StorageRootDetailModel | null): ProjectedAdGroup[] =>
  Array.isArray(overview?.projected_ad_groups) ? overview.projected_ad_groups : [];

export const projectedGroupForLevel = (
  overview: StorageRootDetailModel | null,
  level: 'READ' | 'WRITE'
): ProjectedAdGroup | null =>
  projectedAdGroupsRows(overview).find((row) => String(row?.access_level ?? '').trim().toUpperCase() === level) ?? null;

export const projectedGroupCreated = (row: ProjectedAdGroup | null | undefined): boolean => {
  if (!row) return false;
  const status = String(row.profile_status ?? '').trim().toUpperCase();
  if (status === 'CREATED' || status === 'SUCCEEDED' || status === 'PROVISIONED') return true;
  if (['FAILED', 'ERROR', 'CANCELLED', 'RETRYING', 'RUNNING', 'QUEUED', 'NOT_CREATED'].includes(status)) return false;
  if (typeof row.is_created === 'boolean') return row.is_created;
  return Boolean(String(row.group_external_id ?? '').trim());
};

export const adGroupStatusForLevel = (overview: StorageRootDetailModel | null, level: 'READ' | 'WRITE'): string => {
  const row = projectedGroupForLevel(overview, level);
  if (!row) return 'No group linked';
  const alignment = String(row?.acl_alignment ?? '').trim().toLowerCase();
  if (alignment === 'present') return 'ACL present';
  if (projectedGroupCreated(row)) return 'Created';
  const status = String(row?.profile_status ?? '').trim().toUpperCase();
  if (status === 'RUNNING' || status === 'QUEUED' || status === 'RETRYING') return 'Provisioning';
  if (alignment === 'missing') return 'ACL missing';
  return 'No group linked';
};

export const adGroupStatusTone = (overview: StorageRootDetailModel | null, level: 'READ' | 'WRITE'): 'success' | 'pending' | 'warning' => {
  const status = adGroupStatusForLevel(overview, level);
  if (status === 'ACL present' || status === 'Created') return 'success';
  if (status === 'Provisioning') return 'pending';
  return 'warning';
};

export const buildStorageRootAccessModelRows = (overview: StorageRootDetailModel | null): StorageRootAccessModelRow[] => [
  {
    level: 'read',
    code: 'READ',
    label: 'Read',
    icon: 'bi bi-book',
    tone: 'read',
    users: effectiveAccessCount(overview, 'read'),
    adGroup: adGroupStatusForLevel(overview, 'READ'),
    adGroupTone: adGroupStatusTone(overview, 'READ'),
    groupName: projectedGroupForLevel(overview, 'READ')?.group_name ?? null,
    aclAlignment: projectedGroupForLevel(overview, 'READ')?.acl_alignment ?? null,
    aclPrincipal: projectedGroupForLevel(overview, 'READ')?.acl_principal ?? null
  },
  {
    level: 'write',
    code: 'WRITE',
    label: 'Write',
    icon: 'bi bi-pencil-square',
    tone: 'write',
    users: effectiveAccessCount(overview, 'write'),
    adGroup: adGroupStatusForLevel(overview, 'WRITE'),
    adGroupTone: adGroupStatusTone(overview, 'WRITE'),
    groupName: projectedGroupForLevel(overview, 'WRITE')?.group_name ?? null,
    aclAlignment: projectedGroupForLevel(overview, 'WRITE')?.acl_alignment ?? null,
    aclPrincipal: projectedGroupForLevel(overview, 'WRITE')?.acl_principal ?? null
  }
];

export const ownerDisplayName = (owner: Record<string, unknown>): string =>
  String(
    owner?.displayName ??
    owner?.display_name ??
    owner?.name ??
    owner?.username ??
    owner?.email ??
    'Unknown user'
  );

export const ownersInlineSummary = (owners: Array<Record<string, unknown>>, emptyLabel: string): string => {
  const names = (owners ?? [])
    .map(ownerDisplayName)
    .map((value) => String(value ?? '').trim())
    .filter(Boolean);
  if (names.length === 0) return `0 · ${emptyLabel}`;
  const visible = names.slice(0, 2).join(', ');
  const remaining = names.length - 2;
  return `${names.length} · ${visible}${remaining > 0 ? ` +${remaining}` : ''}`;
};

export const displayStorageRootTags = (
  overview: StorageRootDetailModel | null,
  row: StorageRootRow | null
): StorageRootTagLike[] => (overview?.tags ?? row?.tags ?? []) as StorageRootTagLike[];
