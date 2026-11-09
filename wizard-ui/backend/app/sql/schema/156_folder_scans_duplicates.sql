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

-- Fingerprints of the biggest files of each folder (at most 500 per folder, replaced at each measure): two folders
-- holding the same fingerprint hold the same file (duplicates between folders). Fingerprint = SHA-256 of the size,
-- the first and the last 64 KiB.
CREATE TABLE IF NOT EXISTS storage_root_fingerprints (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  storage_root_id BIGINT NOT NULL,
  fingerprint CHAR(64) NOT NULL,
  size_bytes BIGINT UNSIGNED NOT NULL,
  path VARCHAR(1024) NOT NULL,
  modified_at DATETIME NULL,
  KEY ix_fingerprints_print (fingerprint, size_bytes),
  KEY ix_fingerprints_root (storage_root_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Room taken by duplicates in each measure (5S « Trier », its trend)
SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'storage_root_content_history' AND COLUMN_NAME = 'duplicate_bytes');
SET @sql := IF(@col = 0, 'ALTER TABLE storage_root_content_history ADD COLUMN duplicate_bytes BIGINT UNSIGNED NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Incremental sensitivity scan: where the next scan starts (change time, path) and what is still to read
SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'storage_root_sensitivity' AND COLUMN_NAME = 'content_since');
SET @sql := IF(@col = 0, 'ALTER TABLE storage_root_sensitivity ADD COLUMN content_since VARCHAR(64) NULL, ADD COLUMN content_cursor VARCHAR(1024) NULL, ADD COLUMN content_pending INT NULL, ADD COLUMN content_complete TINYINT(1) NULL, ADD COLUMN rules_version INT NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
