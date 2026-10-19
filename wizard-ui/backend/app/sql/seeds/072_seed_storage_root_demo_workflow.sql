-- ============================================================
-- Minimal demo provisioning jobs for observability/jobs.
-- Keep this seed lightweight and independent from business FKs.
-- ============================================================

SET time_zone = '+00:00';

INSERT INTO provisioning_jobs (
  correlation_id,
  job_type,
  action,
  status,
  storage_root_access_profile_id,
  identity_source_id,
  payload_json,
  result_json,
  metrics_json,
  error_json,
  error_code,
  error_message,
  started_at,
  finished_at
)
VALUES
  (
    'demo-observability-job-queued',
    'AD_GROUP_ENSURE',
    'ensure_ad_group',
    'QUEUED',
    NULL,
    NULL,
    JSON_OBJECT('action', 'ensure_ad_group', 'payload', JSON_OBJECT('template', JSON_OBJECT('slug', 'ensure_ad_group', 'version', 'v1'))),
    JSON_OBJECT(),
    JSON_OBJECT('submitted_by', 'seed', 'watchdog_republish_count', 0),
    JSON_OBJECT(),
    NULL,
    NULL,
    NULL,
    NULL
  ),
  (
    'demo-observability-job-running',
    'ACL_APPLY',
    'acl_apply_via_group',
    'RUNNING',
    NULL,
    NULL,
    JSON_OBJECT('action', 'acl_apply_via_group', 'payload', JSON_OBJECT('template', JSON_OBJECT('slug', 'acl_apply_via_group', 'version', 'v1'))),
    JSON_OBJECT(),
    JSON_OBJECT('submitted_by', 'seed', 'watchdog_republish_count', 1),
    JSON_OBJECT(),
    NULL,
    NULL,
    UTC_TIMESTAMP(),
    NULL
  ),
  (
    'demo-observability-job-failed',
    'SMB_PROBE',
    'test_smb_ntlm',
    'FAILED',
    NULL,
    NULL,
    JSON_OBJECT('action', 'test_smb_ntlm', 'payload', JSON_OBJECT('template', JSON_OBJECT('slug', 'test_smb_ntlm', 'version', 'v1'))),
    JSON_OBJECT(),
    JSON_OBJECT('submitted_by', 'seed', 'watchdog_republish_count', 2),
    JSON_OBJECT('code', 'PROBE_TIMEOUT'),
    'PROBE_TIMEOUT',
    'Synthetic demo job restored for observability/jobs.',
    UTC_TIMESTAMP(),
    UTC_TIMESTAMP()
  )
ON DUPLICATE KEY UPDATE
  job_type = VALUES(job_type),
  action = VALUES(action),
  status = VALUES(status),
  payload_json = VALUES(payload_json),
  result_json = VALUES(result_json),
  metrics_json = VALUES(metrics_json),
  error_json = VALUES(error_json),
  error_code = VALUES(error_code),
  error_message = VALUES(error_message),
  started_at = VALUES(started_at),
  finished_at = VALUES(finished_at);
