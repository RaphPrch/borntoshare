import type { PrincipalSearchItem } from './principal-search';

export type AdSourceOption = {
  id: number;
  name: string;
  canImportGroups: boolean;
  canRunSnapshot: boolean;
  baseDn?: string | null;
  snapshotStatus?: string | null;
  lastSnapshotAt?: string | null;
  usersCount?: number;
  groupsCount?: number;
  objectsCount?: number;
};

const asBool = (value: unknown): boolean => {
  if (typeof value === 'boolean') return value;
  const normalized = String(value ?? '').trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
};

const isAdLike = (row: any): boolean => {
  const type = String(row?.type ?? '').trim().toLowerCase();
  return type === 'ad' || type === 'ldap' || type === 'ldaps';
};

export const toAdSourceOptions = (payload: unknown): AdSourceOption[] =>
  (Array.isArray(payload) ? payload : [])
    .filter((r: any) => {
      if (!isAdLike(r) || r?.is_active === false) return false;
      const status = String(r?.last_snapshot_status ?? '').trim().toUpperCase();
      return status === 'ACTIVE' || status === 'SUCCEEDED';
    })
    .map((r: any) => ({
      id: Number(r?.id ?? 0),
      name: String(r?.name ?? '').trim() || `Source #${String(r?.id ?? '')}`,
      canImportGroups:
        r?.capabilities?.import_groups === undefined
          ? true
          : asBool(r?.capabilities?.import_groups),
      canRunSnapshot: asBool(r?.capabilities?.snapshot_enabled),
      baseDn: String(r?.base_dn ?? r?.baseDn ?? '').trim() || null,
      snapshotStatus: String(r?.last_snapshot_status ?? '').trim() || null,
      lastSnapshotAt: String(r?.last_snapshot_at ?? '').trim() || null,
      usersCount: Number(r?.last_snapshot_users_count ?? 0) || 0,
      groupsCount: Number(r?.last_snapshot_groups_count ?? 0) || 0,
      objectsCount: Number(r?.last_snapshot_objects_count ?? 0) || 0
    }))
    .filter((r: AdSourceOption) => Number.isFinite(r.id) && r.id > 0)
    ;

export const normalizeBrowseUserRows = (
  rows: any[],
  sourceId: number,
  isImportCandidate = false
): PrincipalSearchItem[] => {
  if (!Array.isArray(rows)) return [];

  return rows
    .map((row: any) => {
      const username = String(row?.username ?? '').trim() || null;
      const upn = String(row?.upn ?? '').trim() || null;
      const email = String(row?.mail ?? row?.email ?? '').trim() || null;
      const displayName = String(row?.display_name ?? '').trim() || username || upn || email || 'Identity';
      const stableId = String(row?.id ?? row?.external_id ?? upn ?? username ?? email ?? '').trim();
      if (!stableId) return null;

      return {
        id: stableId,
        type: 'user',
        username,
        upn,
        display_name: displayName,
        email,
        ou: String(row?.ou ?? '').trim() || null,
        group_count: Number(row?.group_count ?? 0) || 0,
        enabled: typeof row?.enabled === 'boolean' ? row.enabled : undefined,
        is_active: typeof row?.enabled === 'boolean' ? row.enabled : undefined,
        auth_source: 'ad',
        external_id: stableId,
        dn: String(row?.dn ?? '').trim() || null,
        identity_source_id: sourceId,
        browse_status: isImportCandidate ? null : (row?.status ?? null),
        is_import_candidate: isImportCandidate
      } as PrincipalSearchItem;
    })
    .filter((item): item is PrincipalSearchItem => Boolean(item));
};

export const snapshotStatusBadge = (item: {
  browse_status?: string | null;
  status?: string | null;
  snapshot_state?: string | null;
  enabled?: boolean;
  is_active?: boolean;
  is_import_candidate?: boolean;
}): { label: string; tone: 'ok' | 'refresh' | 'disabled' | 'candidate' } => {
  if (item.is_import_candidate) return { label: 'Import candidate', tone: 'candidate' };

  const active = item.enabled ?? item.is_active;
  const status = String(item.browse_status ?? item.snapshot_state ?? item.status ?? '').trim().toLowerCase();

  if (active === false || status === 'disabled' || status === 'inactive') {
    return { label: 'Disabled', tone: 'disabled' };
  }
  if (status === 'needs_refresh' || status.includes('refresh') || status.includes('stale') || status.includes('outdated')) {
    return { label: 'Needs refresh', tone: 'refresh' };
  }
  return { label: 'Up-to-date', tone: 'ok' };
};

export const isBrowseEndpointMissing = (error: any): boolean => Number(error?.status ?? 0) === 404;
