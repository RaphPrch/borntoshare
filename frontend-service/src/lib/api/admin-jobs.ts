import type { FetchLike } from './client';
import { apiGetData, apiGetList, apiPostData } from './client';

export type AdminProvisioningJob = {
  id: number;
  correlation_id?: string | null;
  job_type?: string | null;
  action?: string | null;
  status?: string | null;
  storage_root_access_profile_id?: number | null;
  identity_source_id?: number | null;
  payload_json?: Record<string, unknown> | null;
  result_json?: Record<string, unknown> | null;
  metrics_json?: Record<string, unknown> | null;
  error_json?: Record<string, unknown> | null;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  queue_age_seconds?: number | null;
  watchdog_republish_count?: number | null;
  /** Seconds in the queue before a worker took it, and running (still counting while it runs) */
  wait_seconds?: number | null;
  run_seconds?: number | null;
  timeout_seconds?: number | null;
  queue?: string | null;
  attempts?: number | null;
  /** What it worked on, and its page */
  target?: { kind: 'folder' | 'server' | 'directory' | 'host'; id: number | null; label: string; href: string | null; detail?: string } | null;
  origin?: string | null;
  retry_of?: number | null;
  /** queue: nobody took it; running: far beyond its timeout */
  stuck?: 'queue' | 'running' | null;
  retryable?: boolean;
  /** The person who started it (none: the schedule, a policy, the worker) */
  requested_by?: string | null;
  /** A measure of the 5S scanner (lives in the module: no detail, stopped through its folder) */
  external?: boolean;
  progress?: { chunks_total?: number; chunks_done?: number; files?: number; current?: string | null } | null;
  retry_elsewhere?: string | null;
};

export type AdminJobDetail = AdminProvisioningJob & {
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  metrics: Record<string, unknown>;
  error: Record<string, unknown>;
  retried_by: number[];
};

type AdminJobsListParams = {
  status?: string;
  job_type?: string;
  identity_source_id?: number;
  storage_root_access_profile_id?: number;
  active_only?: boolean;
  updated_before_seconds?: number;
  exclude_job_type?: string;
  limit?: number;
};

type AdminJobCancelPayload = {
  reason?: string;
  source?: string;
};

export const listAdminJobs = (
  fetchFn: FetchLike,
  params?: AdminJobsListParams
) =>
  apiGetList<AdminProvisioningJob>(fetchFn, '/admin/jobs', {
    status: params?.status,
    job_type: params?.job_type,
    identity_source_id: params?.identity_source_id,
    storage_root_access_profile_id: params?.storage_root_access_profile_id,
    active_only: params?.active_only,
    updated_before_seconds: params?.updated_before_seconds,
    exclude_job_type: params?.exclude_job_type,
    limit: params?.limit
  });

export const cancelAdminJob = (
  fetchFn: FetchLike,
  jobId: number,
  payload?: AdminJobCancelPayload
) =>
  apiPostData<AdminProvisioningJob>(
    fetchFn,
    `/admin/jobs/${Number(jobId)}/cancel`,
    payload ?? {}
  );

export const getAdminJob = (fetchFn: FetchLike, jobId: number) => apiGetData<AdminJobDetail>(fetchFn, `/admin/jobs/${Number(jobId)}`);

/** A failed or stopped check or scan, started again (a new job linked to the first) */
export const retryAdminJob = (fetchFn: FetchLike, jobId: number) =>
  apiPostData<{ job_id: number | null; retry_of: number; reused: boolean }>(fetchFn, `/admin/jobs/${Number(jobId)}/retry`, {});

/** The stuck jobs (all of them, or some) closed as failed */
export const flushAdminJobs = (fetchFn: FetchLike, jobIds?: number[]) =>
  apiPostData<{ flushed: number[]; failed: Array<{ id: number; message: string }> }>(fetchFn, '/admin/jobs/flush', jobIds?.length ? { job_ids: jobIds } : {});
