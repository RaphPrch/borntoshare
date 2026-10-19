-- Storage root hierarchy support.
--
-- Structural columns, FK and unique key now live in schema/030_storage.sql.
-- This file only backfills normalized_root_path on legacy data.

UPDATE storage_roots
SET normalized_root_path = LOWER(TRIM(TRAILING '/' FROM REPLACE(TRIM(COALESCE(root_path, '')), '\\\\', '/')))
WHERE normalized_root_path IS NULL
   OR TRIM(normalized_root_path) = '';
