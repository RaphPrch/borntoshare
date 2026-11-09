-- The measure of a folder becomes a job of its own (apart from its test), and finds duplicates; the sensitivity
-- scan becomes incremental. Idempotent: can be applied again.

-- State of the last measure of each folder (the folder page shows « measure in progress », its method and duration)
CREATE TABLE IF NOT EXISTS storage_root_scans (
  storage_root_id BIGINT NOT NULL PRIMARY KEY,
  status VARCHAR(16) NOT NULL DEFAULT 'running',
  job_id BIGINT NULL,
  method VARCHAR(16) NULL,
  fallback_reason VARCHAR(300) NULL,
  requested_at DATETIME NULL,
  finished_at DATETIME NULL,
  elapsed_ms BIGINT NULL,
  files BIGINT NULL,
  error_message VARCHAR(600) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- (Fingerprints and the history of the measures moved to the 5S module: b2s_fives_inventory.fingerprints,
-- b2s_fives.content_history, scripts/modules/fives/install.sh)

-- Incremental sensitivity scan: where the next scan starts (change time, path) and what is still to read
SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'storage_root_sensitivity' AND COLUMN_NAME = 'content_since');
SET @sql := IF(@col = 0, 'ALTER TABLE storage_root_sensitivity ADD COLUMN content_since VARCHAR(64) NULL, ADD COLUMN content_cursor VARCHAR(1024) NULL, ADD COLUMN content_pending INT NULL, ADD COLUMN content_complete TINYINT(1) NULL, ADD COLUMN rules_version INT NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
