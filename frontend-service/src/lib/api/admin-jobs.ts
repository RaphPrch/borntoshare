import type { FetchLike } from './client';
import { apiGetList, apiPostData } from './client';

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
};

export type AdminJobsListParams = {
  status?: string;
  job_type?: string;
  identity_source_id?: number;
  storage_root_access_profile_id?: number;
  active_only?: boolean;
  updated_before_seconds?: number;
  limit?: number;
};

export type AdminJobCancelPayload = {
  reason?: string;
  source?: string;
};

export type AdminWatchdogRunPayload = {
  queued_timeout_seconds?: number;
  max_republish_count?: number;
  limit?: number;
};

export type AdminWatchdogRunResult = {
  ok?: boolean;
  queued_timeout_seconds?: number;
  max_republish_count?: number;
  inspected_count?: number;
  republished_count?: number;
  republished_job_ids?: number[];
  failed_count?: number;
  failed_job_ids?: number[];
  skipped?: Array<{ job_id?: number; error?: string }>;
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

export const runAdminJobsWatchdog = (
  fetchFn: FetchLike,
  payload?: AdminWatchdogRunPayload
) =>
  apiPostData<AdminWatchdogRunResult>(
    fetchFn,
    '/admin/jobs/watchdog/run',
    payload ?? {}
  );

