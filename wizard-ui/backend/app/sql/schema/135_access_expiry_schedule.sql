-- Expiry of the granted accesses (Advanced Settings › Infrastructure › Schedules).
-- The requester is removed from the AD group of every expired request, through a worker.
-- Idempotent: can be applied again.

ALTER TABLE infra_schedules DROP CONSTRAINT IF EXISTS chk_infra_schedules_task;
-- The list holds every task known so far: the packs are replayed in order on every deploy, and a narrower
-- list here would refuse the rows of the later ones (dfs_read, 145)
ALTER TABLE infra_schedules
  ADD CONSTRAINT chk_infra_schedules_task CHECK (task IN ('health_check', 'data_sync', 'access_expiry', 'dfs_read'));

INSERT IGNORE INTO infra_schedules (task, is_enabled, interval_minutes, options_json, next_run_at) VALUES
  ('access_expiry', 1, 15, NULL, NULL);
