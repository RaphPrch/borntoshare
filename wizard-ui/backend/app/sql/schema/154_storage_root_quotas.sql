-- Quotas of the governed folders: the FSRM quota on the Windows file server (one row per folder: what was asked,
-- what the server answered on its last reading) and the requests to raise it, decided by an administrator.
-- Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS storage_root_quotas (
  storage_root_id BIGINT NOT NULL PRIMARY KEY,
  -- none: no quota on the server · pending: a change is on its way · applied: the server has it · failed: see error
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  limit_bytes BIGINT UNSIGNED NULL,
  soft_limit TINYINT(1) NOT NULL DEFAULT 0,
  warn_percent TINYINT UNSIGNED NOT NULL DEFAULT 85,
  used_bytes BIGINT UNSIGNED NULL,
  peak_bytes BIGINT UNSIGNED NULL,
  local_path VARCHAR(1024) NULL,
  server_status VARCHAR(64) NULL,
  job_id BIGINT NULL,
  pending_operation VARCHAR(16) NULL,
  error_code VARCHAR(64) NULL,
  error_message VARCHAR(600) NULL,
  read_at DATETIME NULL,
  applied_at DATETIME NULL,
  updated_by VARCHAR(190) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS storage_root_quota_requests (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  storage_root_id BIGINT NOT NULL,
  requested_by_identity_id BIGINT NULL,
  requested_by VARCHAR(190) NULL,
  current_limit_bytes BIGINT UNSIGNED NULL,
  requested_limit_bytes BIGINT UNSIGNED NOT NULL,
  reason VARCHAR(500) NOT NULL,
  -- pending · approved · rejected · cancelled
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  decided_by VARCHAR(190) NULL,
  decided_at DATETIME NULL,
  decision_note VARCHAR(500) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_quota_requests_root (storage_root_id, status),
  KEY ix_quota_requests_status (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
