import { apiPutData, type FetchLike } from './client';

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

export const putGlobalNamingPolicy = (
  fetchFn: FetchLike,
  payload: GlobalNamingPolicy
) => apiPutData<GlobalNamingPolicy>(fetchFn, '/naming-policies/global', payload);
