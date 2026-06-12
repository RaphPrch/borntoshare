/**
 * Zones — V1
 * Keep these types small and stable: they are used by the Zone Console page.
 */

export type ZoneOverview = {
  id: number;
  name: string;
  code?: string | null;
  description?: string | null;
  is_active?: number | boolean | null;
  storage_endpoints_count?: number | null;
  storage_roots_count?: number | null;
};

export type StorageEndpointContextItem = {
  id: number;
  name: string;
  endpoint_type?: string | null;
  zone_id?: number | null;
  host?: string | null;
  port?: number | null;
  status?: string | null;
  is_active?: boolean | null;
};

export type StorageRootContextItem = {
  id: number;
  name: string;
  path?: string | null;
  zone_id?: number | null;
  endpoint_id?: number | null;
  endpoint_name?: string | null;
};

export type AccessProfileSummary = {
  id?: number | null;
  code?: string | null;
  name?: string | null;
  permission?: string | null;
  access_level_code?: string | null;
};

export type EffectivePreview = {
  effective_identity_source_id: number | null;
  effective_identity_source_name: string | null;
  effective_ou_dn: string | null;
  warnings: string[];
};

export type ZoneProvisioningPolicy = {
  enabled: boolean;
  identity_source_mode: "inherit" | "fixed";
  identity_source_id: number | null;
  ou_strategy: "identity_default" | "zone_static";
  static_ou_dn: string | null;
  effective_preview: EffectivePreview;
};
