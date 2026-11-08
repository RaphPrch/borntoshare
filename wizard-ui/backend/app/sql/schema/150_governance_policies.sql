-- Smart policies: « if the folders match this condition, then do this » (tag, alert, notice to the guardians).
-- The condition is written in the language of the express search of the folders (est:sensible, tag:…, taille>…).
-- A hit remembers that a folder matches a policy: the actions run once when it starts matching, the alert closes
-- when it stops. Evaluated by the scheduler (task « policies », every 15 minutes). Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS governance_policies (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  description VARCHAR(500) NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  condition_query VARCHAR(500) NOT NULL,
  actions_json JSON NOT NULL,
  last_run_at DATETIME NULL,
  last_matched INT NULL,
  last_new INT NULL,
  last_error VARCHAR(500) NULL,
  created_by VARCHAR(190) NULL,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS governance_policy_hits (
  policy_id BIGINT NOT NULL,
  storage_root_id BIGINT NOT NULL,
  first_matched_at DATETIME NOT NULL,
  last_matched_at DATETIME NOT NULL,
  PRIMARY KEY (policy_id, storage_root_id),
  KEY ix_governance_policy_hits_root (storage_root_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE infra_schedules DROP CONSTRAINT IF EXISTS chk_infra_schedules_task;
ALTER TABLE infra_schedules
  ADD CONSTRAINT chk_infra_schedules_task CHECK (task IN ('health_check', 'data_sync', 'access_expiry', 'dfs_read', 'policies'));

INSERT IGNORE INTO infra_schedules (task, is_enabled, interval_minutes, options_json, next_run_at) VALUES
  ('policies', 1, 15, NULL, NULL);
