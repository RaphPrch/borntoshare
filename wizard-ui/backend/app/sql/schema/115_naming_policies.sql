-- Group naming policy: the global rule (scope_type 'global', scope_id 0) and the overrides of a zone, an
-- endpoint or a folder (NULL = inherited from the global rule).
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

-- The global rule exists from the start (the zone view joins it); NULL = the default of the application
INSERT IGNORE INTO naming_policies (scope_type, scope_id, override_enabled, group_prefix, template, normalize_uppercase, max_sam_length, rootcode_strategy)
VALUES ('global', 0, 1, 'B2S', '{PREFIX}_{ROOTCODE}_{PERM}', 1, 64, 'BASENAME');
