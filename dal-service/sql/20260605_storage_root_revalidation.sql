SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE storage_roots ADD COLUMN needs_revalidation BOOLEAN NOT NULL DEFAULT FALSE',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = @schema_name
    AND table_name = 'storage_roots'
    AND column_name = 'needs_revalidation'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE storage_roots ADD COLUMN revalidation_reason VARCHAR(512) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = @schema_name
    AND table_name = 'storage_roots'
    AND column_name = 'revalidation_reason'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_storage_roots_endpoint_normalized_path ON storage_roots (storage_endpoint_id, normalized_root_path)',
    'SELECT 1'
  )
  FROM information_schema.statistics
  WHERE table_schema = @schema_name
    AND table_name = 'storage_roots'
    AND index_name = 'idx_storage_roots_endpoint_normalized_path'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_storage_roots_revalidation ON storage_roots (needs_revalidation, storage_endpoint_id)',
    'SELECT 1'
  )
  FROM information_schema.statistics
  WHERE table_schema = @schema_name
    AND table_name = 'storage_roots'
    AND index_name = 'idx_storage_roots_revalidation'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
