import { apiGetData, apiPostData, apiPutData, type FetchLike } from './client';

export type ExtensionKey = 'syslog' | 'splunk' | 'centreon';
export type ExtensionRoutes = { audit: boolean; alerts: boolean; min_severity: 'info' | 'warning' | 'high' | 'critical' };
export type ExtensionStats = { sent: number; failed: number; last_status: string; last_at: string; last_detail: string | null; buckets: number[]; failed_buckets: number[] };
export type Extension = {
  key: ExtensionKey;
  events: string[];
  enabled: boolean;
  configured: boolean;
  config: Record<string, any>;
  routes: ExtensionRoutes;
  has_secret: boolean;
  stats: ExtensionStats | null;
};
export type ExtensionDelivery = { id: number; ext_key: ExtensionKey; event_type: string; summary: string; status: 'delivered' | 'failed'; detail: string | null; attempts: number; latency_ms: number | null; created_at: string };
export type ExtensionWrite = { enabled: boolean; config: Record<string, any>; routes: ExtensionRoutes; secret?: string | null };

export const listExtensions = (fetchFn: FetchLike) => apiGetData<{ extensions: Extension[]; health_path: string }>(fetchFn, '/extensions');
export const saveExtension = (fetchFn: FetchLike, key: ExtensionKey, payload: ExtensionWrite) =>
  apiPutData<{ key: string; enabled: boolean; token: string | null }>(fetchFn, `/extensions/${key}`, payload);
export const testExtension = (fetchFn: FetchLike, key: ExtensionKey, payload: ExtensionWrite) =>
  apiPostData<{ ok: boolean; latency_ms?: number; error?: string }>(fetchFn, `/extensions/${key}/test`, payload);
export const renewCentreonToken = (fetchFn: FetchLike) => apiPostData<{ token: string }>(fetchFn, '/extensions/centreon/token', {});
export const listExtensionDeliveries = (fetchFn: FetchLike) => apiGetData<ExtensionDelivery[]>(fetchFn, '/extensions/deliveries', { limit: 50 });
