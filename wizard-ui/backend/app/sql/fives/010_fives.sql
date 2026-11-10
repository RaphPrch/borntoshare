-- Database b2s_fives of the 5S module: what it computes over time (history of the measures, its settings, its scans).
-- Applied by the migration account (wizard, make deploy); the module only reads and writes. Idempotent.

CREATE TABLE IF NOT EXISTS content_history (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  storage_root_id BIGINT NOT NULL,
  measured_at DATETIME NOT NULL,
  bytes BIGINT UNSIGNED NOT NULL,
  files INT UNSIGNED NULL,
  folders INT UNSIGNED NULL,
  cold_1y_bytes BIGINT UNSIGNED NULL,
  cold_3y_bytes BIGINT UNSIGNED NULL,
  junk_bytes BIGINT UNSIGNED NULL,
  duplicate_bytes BIGINT UNSIGNED NULL,
  UNIQUE KEY ux_content_history_root_hour (storage_root_id, measured_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS module_settings (
  setting_key VARCHAR(64) NOT NULL PRIMARY KEY,
  value_json LONGTEXT NULL,
  updated_by VARCHAR(190) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scan_runs (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  storage_root_id BIGINT NOT NULL,
  host VARCHAR(255) NOT NULL,
  -- queued · running · done · failed · delegated (measured by the worker of the core through SMB) · cancelled
  status VARCHAR(16) NOT NULL DEFAULT 'queued',
  reason VARCHAR(16) NOT NULL DEFAULT 'manual',
  mode VARCHAR(16) NULL,
  requested_by VARCHAR(190) NULL,
  requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at DATETIME NULL,
  heartbeat_at DATETIME NULL,
  finished_at DATETIME NULL,
  scanner_id VARCHAR(64) NULL,
  attempts INT NOT NULL DEFAULT 0,
  progress_json LONGTEXT NULL,
  summary_json LONGTEXT NULL,
  error_message VARCHAR(600) NULL,
  KEY ix_scan_runs_queue (status, requested_at),
  KEY ix_scan_runs_root (storage_root_id, status),
  KEY ix_scan_runs_host (host, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scan_chunks (
  storage_root_id BIGINT NOT NULL,
  chunk_key VARCHAR(255) NOT NULL,
  stats_json LONGTEXT NOT NULL,
  run_id BIGINT NULL,
  scanned_at DATETIME NOT NULL,
  PRIMARY KEY (storage_root_id, chunk_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scan_state (
  storage_root_id BIGINT NOT NULL PRIMARY KEY,
  local_path VARCHAR(1024) NULL,
  volume VARCHAR(16) NULL,
  journal_id VARCHAR(32) NULL,
  next_usn BIGINT NULL,
  last_full_at DATETIME NULL,
  last_done_at DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
