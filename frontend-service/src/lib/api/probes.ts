import type { FetchLike } from './client';
import { apiGetData, apiPostData } from './client';

/* =========================================================
 * Enums alignés backend (UnifiedProbeRequest)
 * ========================================================= */

export type ProbeKind =
  | 'identity-source'
  | 'storage-endpoint'
  | 'storage-root'
  | 'acl';

export type ProbeProtocol =
  | 'ldap'
  | 'ldaps'
  | 'smb'
  | 'acl_push';

export type ProbeScope =
  | 'connect'
  | 'read'
  | 'write';

/* =========================================================
 * Request payload (frontend → governance)
 * ========================================================= */

export type ProbeRunRequest = {
  kind: ProbeKind;
  protocol: ProbeProtocol;
  scope?: ProbeScope;

  target: Record<string, any>;

  auth?: {
    mode?: 'none' | 'basic' | 'ntlm' | 'kerberos' | 'simple';
    username?: string;
    domain?: string;
    secret_ref?: string;
    password?: string;
  };

  options?: {
    timeout_sec?: number;
    verify_tls?: boolean;
    test_write?: boolean;
    dns_check?: boolean;
    dry_run?: boolean;
    discover?: boolean;
    discover_permissions?: boolean;
  };

  context?: {
    zone_id?: number;
    identity_source_id?: number;
    storage_endpoint_id?: number;
    storage_root_id?: number;
    storage_root_name?: string;
    ui_origin?: 'wizard' | 'admin';
  };
};

/* =========================================================
 * Probe job (governance → frontend)
 * ========================================================= */

export type ProbeJobStatus =
  | 'queued'
  | 'running'
  | 'retrying'
  | 'success'
  | 'succeeded'
  | 'failed'
  | 'partial'
  | 'cancelled'
  | 'timed_out'
  | 'timeout';

export type ProbeJob = {
  job_id: string;
  type?: string;
  status: ProbeJobStatus;
  created_at?: number;
  started_at?: number;
  finished_at?: number;
  progress?: Record<string, any>;
  result?: any;
  error?: {
    message?: string;
    [key: string]: any;
  };
};

/* =========================================================
 * API helpers
 * ========================================================= */

export const runProbeJob = (
  fetchFn: FetchLike,
  payload: ProbeRunRequest,
) =>
  apiPostData<{ job_id: string; status: 'queued' | 'running'; poll_url: string }>(
    fetchFn,
    '/probes/run',
    payload,
    {
      timeoutMs: 45_000,
    },
  );

export const getProbeJob = (
  fetchFn: FetchLike,
  jobId: string,
) =>
  apiGetData<ProbeJob>(
    fetchFn,
    `/probes/jobs/${jobId}`,
  );
