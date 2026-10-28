// Advanced Settings › Infrastructure (core-service /infrastructure, platform administrators)
import type { FetchLike } from './client';
import { apiDelete, apiDeleteData, apiGetData, apiGetList, apiPatchData, apiPost, apiPostData, apiPut, apiPutData } from './client';

export type HealthStatus = 'healthy' | 'degraded' | 'down' | 'unknown';

export type HistoryPoint = { status: HealthStatus; latency_ms: number | null; at: string };

export type InfraComponent = {
  component: string;
  label: string;
  category: string;
  status: HealthStatus;
  stale: boolean;
  latency_ms: number | null;
  message: string | null;
  checked_by: string | null;
  checked_at: string | null;
  details: Record<string, unknown>;
  uptime_24h: number | null;
  history: HistoryPoint[];
};

export type InfraWorker = {
  id: number;
  name: string;
  host: string;
  port: number;
  use_tls: boolean;
  verify_tls: boolean;
  username: string;
  is_enabled: boolean;
  status: HealthStatus;
  last_check_at: string | null;
  last_seen_at: string | null;
  last_message: string | null;
  version: string | null;
  hostname: string | null;
  max_scope: string | null;
  has_password: boolean;
  agent_url: string;
  details: {
    worker_processes?: number;
    uptime_seconds?: number;
    broker?: { reachable?: boolean; latency_ms?: number; queues?: Record<string, number> };
    ldap_tls_verify?: boolean;
    ldap_ca_file_present?: boolean;
    agent_tls?: boolean;
  };
};

export type WorkerInput = {
  name: string;
  host: string;
  port: number;
  use_tls: boolean;
  verify_tls: boolean;
  username: string;
  password_ref?: string | null;
  is_enabled?: boolean;
};

export type AgentCheck = { status: HealthStatus; message: string; latency_ms: number | null; details: InfraWorker['details'] };

export type DatabaseSettings = {
  mode: 'fields' | 'dsn';
  host: string;
  port: number;
  name: string;
  user: string;
  logging_name?: string | null;
};

export type DatabaseInfo = {
  running: DatabaseSettings & { source: 'env' | 'runtime' };
  configured: (Partial<DatabaseSettings> & { has_password?: boolean; updated_at?: string; updated_by?: string }) | null;
  pending_restart: boolean;
  runtime_dir: string;
  runtime_dir_writable: boolean;
};

export type DatabaseInput = {
  mode: 'fields' | 'dsn';
  host?: string;
  port?: number;
  name?: string;
  user?: string;
  password?: string;
  logging_name?: string;
  dsn?: string;
  logging_dsn?: string;
};

export type DatabaseTest = {
  ok: boolean;
  message: string;
  latency_ms?: number;
  version?: string;
  tables?: number;
  missing_tables?: string[];
};

export type ScheduleTask = 'health_check' | 'data_sync';

export type InfraSchedule = {
  task: ScheduleTask;
  is_enabled: boolean;
  interval_minutes: number;
  options: { snapshots?: boolean; shares?: boolean; acl_drift?: boolean };
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: 'running' | 'success' | 'partial' | 'failed' | null;
  last_message: string | null;
  last_summary: Record<string, unknown>;
};

export type InfraService = {
  id: number;
  component_key: string;
  label: string;
  category: string;
  check_kind: 'http' | 'tcp';
  target: string;
  is_builtin: boolean;
  is_enabled: boolean;
};

export type ServiceInput = Pick<InfraService, 'label' | 'category' | 'check_kind' | 'target' | 'is_enabled'>;

export type InfraOverview = {
  components: InfraComponent[];
  summary: Record<HealthStatus, number> & { total: number };
  generated_at: string;
  workers: InfraWorker[];
  schedules: InfraSchedule[];
  database: DatabaseInfo;
};

export const getInfraOverview = (fetchFn: FetchLike) => apiGetData<InfraOverview>(fetchFn, '/infrastructure/overview');

export const testDatabase = (fetchFn: FetchLike, body: DatabaseInput) =>
  apiPostData<DatabaseTest>(fetchFn, '/infrastructure/database/test', body, { timeoutMs: 20000 });
export const saveDatabase = (fetchFn: FetchLike, body: DatabaseInput) =>
  apiPutData<DatabaseInfo & { test: DatabaseTest }>(fetchFn, '/infrastructure/database', body);
export const resetDatabase = (fetchFn: FetchLike) => apiDeleteData<DatabaseInfo>(fetchFn, '/infrastructure/database');

export const testWorker = (fetchFn: FetchLike, body: WorkerInput & { worker_id?: number }) =>
  apiPostData<AgentCheck>(fetchFn, '/infrastructure/workers/test', body, { timeoutMs: 20000 });
export const createWorker = (fetchFn: FetchLike, body: WorkerInput) =>
  apiPostData<InfraWorker>(fetchFn, '/infrastructure/workers', body, { timeoutMs: 20000 });
export const updateWorker = (fetchFn: FetchLike, id: number, body: Partial<WorkerInput>) =>
  apiPatchData<InfraWorker>(fetchFn, `/infrastructure/workers/${id}`, body);
export const deleteWorker = (fetchFn: FetchLike, id: number) => apiDeleteData<{ ok: boolean }>(fetchFn, `/infrastructure/workers/${id}`);
export const checkWorker = (fetchFn: FetchLike, id: number) =>
  apiPostData<InfraWorker>(fetchFn, `/infrastructure/workers/${id}/check`, {}, { timeoutMs: 20000 });

export const updateSchedule = (
  fetchFn: FetchLike,
  task: ScheduleTask,
  body: { is_enabled?: boolean; interval_minutes?: number; options?: InfraSchedule['options'] }
) => apiPutData<InfraSchedule>(fetchFn, `/infrastructure/schedules/${task}`, body);
export const runSchedule = (fetchFn: FetchLike, task: ScheduleTask) =>
  apiPostData<{ task: ScheduleTask; status: string; message: string }>(fetchFn, `/infrastructure/schedules/${task}/run`, {}, { timeoutMs: 60000 });

export const listInfraServices = (fetchFn: FetchLike) => apiGetList<InfraService>(fetchFn, '/infrastructure/services');
// The mutations answer with the full list; callers reload it with listInfraServices
export const createInfraService = (fetchFn: FetchLike, body: ServiceInput) =>
  apiPost<unknown>(fetchFn, '/infrastructure/services', body);
export const updateInfraService = (fetchFn: FetchLike, id: number, body: ServiceInput) =>
  apiPut<unknown>(fetchFn, `/infrastructure/services/${id}`, body);
export const deleteInfraService = (fetchFn: FetchLike, id: number) =>
  apiDelete<unknown>(fetchFn, `/infrastructure/services/${id}`);
