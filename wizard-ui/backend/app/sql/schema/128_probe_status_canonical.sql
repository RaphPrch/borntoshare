-- Probe status data canonicalization.
--
-- Structural CHECK constraints now live in schema/030_storage.sql.
-- This file only normalizes legacy data sets.

UPDATE storage_endpoints
SET last_probe_status = CASE
  WHEN last_probe_status IS NULL THEN NULL
  WHEN TRIM(last_probe_status) = '' THEN NULL
  WHEN LOWER(TRIM(last_probe_status)) IN ('success', 'running', 'failed', 'unknown') THEN LOWER(TRIM(last_probe_status))
  ELSE 'unknown'
END;

UPDATE storage_roots
SET last_probe_status = CASE
  WHEN last_probe_status IS NULL THEN NULL
  WHEN TRIM(last_probe_status) = '' THEN NULL
  WHEN LOWER(TRIM(last_probe_status)) IN ('success', 'running', 'failed', 'unknown') THEN LOWER(TRIM(last_probe_status))
  ELSE 'unknown'
END;
