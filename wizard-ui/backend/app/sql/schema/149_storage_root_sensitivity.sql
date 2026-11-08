-- Sensitivity scan of each governed folder (passwords, keys, vaults stored in it), by the capsule runner.
-- Only the path of the files, the rule, the line and a masked excerpt are kept, never the secret.
-- Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS storage_root_sensitivity (
  storage_root_id BIGINT NOT NULL PRIMARY KEY,
  status VARCHAR(16) NOT NULL,
  files_flagged INT NOT NULL DEFAULT 0,
  counts_json JSON NULL,
  findings_json JSON NULL,
  summary_json JSON NULL,
  error_message VARCHAR(500) NULL,
  job_id BIGINT NULL,
  requested_at DATETIME NULL,
  scanned_at DATETIME NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY ix_storage_root_sensitivity_flagged (files_flagged)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
