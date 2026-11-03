-- Reading of every DFS namespace (Advanced Settings › Infrastructure › Schedules): DFS folders changed outside
-- BornToShare show without « Read again ». Every 6 hours by default.
-- Idempotent: can be applied again.

ALTER TABLE infra_schedules DROP CONSTRAINT IF EXISTS chk_infra_schedules_task;
ALTER TABLE infra_schedules
  ADD CONSTRAINT chk_infra_schedules_task CHECK (task IN ('health_check', 'data_sync', 'access_expiry', 'dfs_read'));

INSERT IGNORE INTO infra_schedules (task, is_enabled, interval_minutes, options_json, next_run_at) VALUES
  ('dfs_read', 1, 360, NULL, NULL);
