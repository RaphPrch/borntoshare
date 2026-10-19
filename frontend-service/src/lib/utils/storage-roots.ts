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
  pending_validation_count?: number | null;
  effective_availability?: string | null;
  needs_revalidation?: boolean | number | null;
  revalidation_reason?: string | null;
  tags?: StorageRootTagLike[];
  [key: string]: unknown;
};

export const normalizeStorageRootRow = (row: any): StorageRootRow => ({
  ...row,
  storage_root_id: Number(row?.storage_root_id ?? row?.id ?? 0),
  storage_root_name: row?.storage_root_name ?? row?.name ?? null,
  storage_root_code: row?.storage_root_code ?? row?.code ?? null
});
