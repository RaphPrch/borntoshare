import { apiGetList, apiPostData, type FetchLike } from './client';

export type ActivityEvent = {
  id?: number | string;
  action?: string;
  actor_id?: string;
  actor_type?: string;
  target_display?: string;
  created_at?: string;
  event_time?: string;
  severity?: string;
  result?: string;
  outcome?: string;
  details_changes?: Array<{ field?: string; from?: string; to?: string }>;
  context_json?: Record<string, unknown> | null;
  metadata_json?: Record<string, unknown> | null;
  [k: string]: unknown;
};

export type ActivityEventCreatePayload = {
  action: string;
  outcome?: 'success' | 'failed' | 'warning' | string;
  severity?: 'info' | 'admin' | 'critical' | string;
  target_type?: string;
  target_id?: number | string;
  target_display?: string;
  zone_id?: number | string;
  endpoint_id?: number | string;
  root_id?: number | string;
  context_json?: Record<string, unknown>;
  metadata_json?: Record<string, unknown>;
};

export type ActivityEventCreateResponse = {
  id?: number | string;
  ok?: boolean;
};

export const listActivityByTarget = async (
  fetchFn: FetchLike,
  targetType: string,
  targetId?: number | string,
  limit = 50
): Promise<ActivityEvent[]> =>
  apiGetList<ActivityEvent>(fetchFn, '/activity/by-target', {
    target_type: targetType,
    target_id: targetId,
    limit
  });

export const listActivityLatest = async (
  fetchFn: FetchLike,
  limit = 200,
  businessOnly = false
): Promise<ActivityEvent[]> =>
  apiGetList<ActivityEvent>(fetchFn, '/activity/latest', {
    limit,
    business_only: businessOnly
  });

export const createActivityEvent = async (
  fetchFn: FetchLike,
  payload: ActivityEventCreatePayload
): Promise<ActivityEventCreateResponse> => {
  return apiPostData<ActivityEventCreateResponse>(fetchFn, '/activity/events', payload);
};
