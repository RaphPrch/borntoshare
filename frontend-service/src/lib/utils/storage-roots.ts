export type StorageRootTagLike = {
  id?: number | string;
  tag_id?: number | string;
  label?: string | null;
  name?: string | null;
  code?: string | null;
  color?: string | null;
  color_rgb?: string | null;
};

export type StorageRootRow = {
  storage_root_id: number;
  storage_root_name?: string | null;
  storage_root_code?: string | null;
  zone_id?: number | string | null;
  zone_name?: string | null;
  storage_endpoint_name?: string | null;
  root_path?: string | null;
  normalized_root_path?: string | null;
  parent_storage_root_id?: number | string | null;
  parent_storage_root_name?: string | null;
  parent_root_path?: string | null;
  inherit_owners?: boolean | number | null;
  inherit_tags?: boolean | number | null;
  /** @deprecated Legacy compatibility flag still accepted from DAL payloads. */
  inherit_access_profiles?: boolean | number | null;
  pending_validation_count?: number | null;
  effective_availability?: string | null;
  needs_revalidation?: boolean | number | null;
  revalidation_reason?: string | null;
  tags?: StorageRootTagLike[];
  [key: string]: unknown;
};

export type StorageRootZoneNode = {
  zone_id: number;
  zone_name: string;
  roots: StorageRootRow[];
};

export const normalizeStorageRootRow = (row: any): StorageRootRow => ({
  ...row,
  storage_root_id: Number(row?.storage_root_id ?? row?.id ?? 0),
  storage_root_name: row?.storage_root_name ?? row?.name ?? null,
  storage_root_code: row?.storage_root_code ?? row?.code ?? null
});

export const buildStorageRootTree = (rows: StorageRootRow[]): StorageRootZoneNode[] => {
  const byZone = new Map<number, StorageRootZoneNode>();

  for (const row of rows ?? []) {
    const zoneId = Number(row?.zone_id ?? 0);

    if (!byZone.has(zoneId)) {
      byZone.set(zoneId, {
        zone_id: zoneId,
        zone_name: String(row?.zone_name ?? 'Unassigned zone'),
        roots: []
      });
    }

    byZone.get(zoneId)!.roots.push(row);
  }

  return [...byZone.values()]
    .map((zone) => ({
      ...zone,
      roots: [...zone.roots].sort((a, b) =>
        String(a?.storage_root_name ?? a?.storage_root_code ?? '')
          .localeCompare(String(b?.storage_root_name ?? b?.storage_root_code ?? ''), 'fr', { sensitivity: 'base' })
      )
    }))
    .sort((a, b) =>
      String(a.zone_name ?? '').localeCompare(String(b.zone_name ?? ''), 'fr', { sensitivity: 'base' })
    );
};
