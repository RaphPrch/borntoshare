-- Sensitivity scan: files marked « false positive » by an administrator. They stay listed but no longer count
-- (counters, est:sensible, policies), across the next scans. Idempotent: can be applied again.

ALTER TABLE storage_root_sensitivity ADD COLUMN IF NOT EXISTS ignored_json JSON NULL;
