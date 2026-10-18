type AdSourceOption = {
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
