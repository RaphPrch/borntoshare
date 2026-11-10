-- Two tables less, nothing lost (idempotent: applied again, it does nothing):
-- - governance_events: written, never read; each job keeps its outcome in provisioning_jobs and the audit
--   journal (borntoshare_logging) keeps the failures and cancellations;
-- - naming_policy_global and naming_policy_overrides become naming_policies (the global rule is its 'global' row).

DROP TABLE IF EXISTS governance_events;

CREATE TABLE IF NOT EXISTS naming_policies (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  scope_type VARCHAR(32) NOT NULL,
  scope_id BIGINT UNSIGNED NOT NULL,
  override_enabled TINYINT(1) NOT NULL DEFAULT 0,
  group_prefix VARCHAR(32) NULL,
  template VARCHAR(128) NULL,
  normalize_uppercase TINYINT(1) NULL,
  max_sam_length INT NULL,
  replace_map_json TEXT NULL,
  rootcode_strategy VARCHAR(32) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_naming_policies_scope UNIQUE (scope_type, scope_id),
  CONSTRAINT ck_naming_policies_scope_type CHECK (scope_type IN ('global', 'zone', 'storage_endpoint', 'storage_root'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @o := (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'naming_policy_overrides');
SET @sql := IF(@o = 1, 'INSERT IGNORE INTO naming_policies (scope_type, scope_id, override_enabled, group_prefix, template, normalize_uppercase, max_sam_length, replace_map_json, rootcode_strategy, created_at, updated_at) SELECT scope_type, scope_id, override_enabled, group_prefix, template, normalize_uppercase, max_sam_length, replace_map_json, rootcode_strategy, created_at, updated_at FROM naming_policy_overrides', 'SELECT 1');
PREPARE s FROM @sql;
EXECUTE s;
DEALLOCATE PREPARE s;
SET @sql := IF(@o = 1, 'DROP TABLE naming_policy_overrides', 'SELECT 1');
PREPARE s FROM @sql;
EXECUTE s;
DEALLOCATE PREPARE s;

SET @g := (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'naming_policy_global');
SET @sql := IF(@g = 1, 'INSERT INTO naming_policies (scope_type, scope_id, override_enabled, group_prefix, template, normalize_uppercase, max_sam_length, replace_map_json, rootcode_strategy, updated_at) SELECT ''global'', 0, 1, group_prefix, template, normalize_uppercase, max_sam_length, replace_map_json, rootcode_strategy, updated_at FROM naming_policy_global WHERE id = 1 ON DUPLICATE KEY UPDATE group_prefix = VALUES(group_prefix), template = VALUES(template), normalize_uppercase = VALUES(normalize_uppercase), max_sam_length = VALUES(max_sam_length), replace_map_json = VALUES(replace_map_json), rootcode_strategy = VALUES(rootcode_strategy)', 'SELECT 1');
PREPARE s FROM @sql;
EXECUTE s;
DEALLOCATE PREPARE s;
SET @sql := IF(@g = 1, 'DROP TABLE naming_policy_global', 'SELECT 1');
PREPARE s FROM @sql;
EXECUTE s;
DEALLOCATE PREPARE s;

-- The global rule, also when there was none before (the zone view joins it)
INSERT IGNORE INTO naming_policies (scope_type, scope_id, override_enabled, group_prefix, template, normalize_uppercase, max_sam_length, rootcode_strategy)
VALUES ('global', 0, 1, 'B2S', '{PREFIX}_{ROOTCODE}_{PERM}', 1, 64, 'BASENAME');
-- The view that read the two old tables is defined again by make deploy (VIEWS: 141_views_naming_policy_effective)
