import { apiGetData, apiPatchData, apiPostData, apiPutData, type FetchLike } from './client';

export type RootcodeStrategy = 'BASENAME' | 'PATH_ALL';

export type GlobalNamingPolicy = {
  id?: number;
  group_prefix: string;
  template: string;
  normalize_uppercase: boolean;
  max_sam_length: number;
  replace_map_json: string | Record<string, string>;
  rootcode_strategy: RootcodeStrategy;
};

export type ZoneNamingPolicy = {
  zone_id: number;
  override_enabled: boolean;
  group_prefix: string | null;
  template: string | null;
  normalize_uppercase: boolean | null;
  max_sam_length: number | null;
  replace_map_json: string | Record<string, string> | null;
  rootcode_strategy: RootcodeStrategy | null;
};

export type ZoneGovernanceSettings = {
  id: number;
  name: string;
  code: string | null;
  description: string | null;
};

export type NamingPreviewPayload = {
  zone_id: number | string;
  storage_root_path: string;
  perm: string;
  profile?: string;
};

export type NamingPreviewResult = {
  samAccountName: string;
  cn?: string;
};

export const getGlobalNamingPolicy = (fetchFn: FetchLike) =>
  apiGetData<GlobalNamingPolicy>(fetchFn, '/naming-policies/global');

export const putGlobalNamingPolicy = (
  fetchFn: FetchLike,
  payload: GlobalNamingPolicy
) => apiPutData<GlobalNamingPolicy>(fetchFn, '/naming-policies/global', payload);

export const getZoneNamingPolicy = (fetchFn: FetchLike, zoneId: number) =>
  apiGetData<ZoneNamingPolicy>(fetchFn, `/naming-policies/zones/${zoneId}`);

export const putZoneNamingPolicy = (
  fetchFn: FetchLike,
  zoneId: number,
  payload: Omit<ZoneNamingPolicy, 'zone_id'>
) => apiPutData<ZoneNamingPolicy>(fetchFn, `/naming-policies/zones/${zoneId}`, payload);

export const getZoneGovernanceSettings = (fetchFn: FetchLike, zoneId: number) =>
  apiGetData<ZoneGovernanceSettings>(fetchFn, `/zones/${zoneId}`);

export const patchZoneGovernanceSettings = (
  fetchFn: FetchLike,
  zoneId: number,
  payload: Partial<ZoneGovernanceSettings>
) => apiPatchData<{ ok: true }>(fetchFn, `/zones/${zoneId}`, payload);

export const previewNamingPolicy = (fetchFn: FetchLike, payload: NamingPreviewPayload) =>
  apiPostData<NamingPreviewResult>(fetchFn, '/naming-policies/preview', payload);
