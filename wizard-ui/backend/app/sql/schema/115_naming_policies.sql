CREATE TABLE IF NOT EXISTS naming_policy_global (
  id TINYINT UNSIGNED NOT NULL DEFAULT 1,
  group_prefix VARCHAR(32) NOT NULL DEFAULT 'B2S',
  template VARCHAR(128) NOT NULL DEFAULT '{PREFIX}_{ROOTCODE}_{PERM}',
  normalize_uppercase TINYINT(1) NOT NULL DEFAULT 1,
  max_sam_length INT NOT NULL DEFAULT 64,
  replace_map_json TEXT NULL,
  rootcode_strategy VARCHAR(32) NOT NULL DEFAULT 'BASENAME',
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS naming_policy_overrides (
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
  CONSTRAINT uq_naming_policy_overrides_scope UNIQUE (scope_type, scope_id),
  CONSTRAINT ck_naming_policy_overrides_scope_type CHECK (scope_type IN ('zone', 'storage_endpoint', 'storage_root'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
