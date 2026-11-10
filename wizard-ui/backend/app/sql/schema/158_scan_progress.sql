-- The measures done by the scanner of the 5S module report their progress (pieces walked, files) and their mode
-- (full or incremental through the NTFS change journal) to the folder page. Idempotent: can be applied again.
SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'storage_root_scans' AND COLUMN_NAME = 'progress_json');
SET @sql := IF(@col = 0, 'ALTER TABLE storage_root_scans ADD COLUMN progress_json LONGTEXT NULL, ADD COLUMN mode VARCHAR(16) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
