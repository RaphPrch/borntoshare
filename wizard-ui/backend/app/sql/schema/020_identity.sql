CREATE TABLE IF NOT EXISTS identity_sources (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  type VARCHAR(32) NOT NULL,
  name VARCHAR(190) NOT NULL,
  domain_name VARCHAR(255) NULL,
  protocol VARCHAR(16) NULL,
  host VARCHAR(190) NULL,
  port INT NULL,
  base_dn VARCHAR(512) NULL,
  bind_dn VARCHAR(512) NULL,
  bind_password_ref VARCHAR(512) NULL,
  default_group_ou_dn VARCHAR(512) NULL,
  issuer_url VARCHAR(512) NULL,
  capabilities JSON NOT NULL DEFAULT (JSON_OBJECT()),
  write_enabled TINYINT(1) NOT NULL DEFAULT 0,
  auth_enabled TINYINT(1) NOT NULL DEFAULT 0,
  auth_priority INT NOT NULL DEFAULT 100,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  external_id VARCHAR(255) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'disabled',
  last_probe_at DATETIME NULL,
  last_probe_message VARCHAR(512) NULL,
  last_snapshot_at DATETIME NULL,
  last_snapshot_version INT UNSIGNED NULL,
  last_usn_changed BIGINT UNSIGNED NULL,
  last_dirsync_cookie TEXT NULL,
  snapshot_mode VARCHAR(32) NOT NULL DEFAULT 'full',
  delta_supported TINYINT(1) NOT NULL DEFAULT 0,
  dirsync_supported TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS identities (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  source_id BIGINT UNSIGNED NOT NULL,
  username VARCHAR(255) NULL,
  type VARCHAR(16) NOT NULL,
  external_id VARCHAR(255) NOT NULL,
  display_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NULL,
  auth_source VARCHAR(64) NOT NULL DEFAULT 'external',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  snapshot_version INT UNSIGNED NOT NULL DEFAULT 1,
  snapshot_source VARCHAR(64) NULL,
  provisioning_source VARCHAR(32) NOT NULL DEFAULT 'explicit',
  snapshot_hash CHAR(64) NULL,
  last_snapshot_at DATETIME(6) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_identities_source_external_id UNIQUE (source_id, external_id),
  KEY idx_identities_source_username (source_id, username),
  CONSTRAINT fk_identities_source_id FOREIGN KEY (source_id) REFERENCES identity_sources(id)
);

CREATE TABLE IF NOT EXISTS local_credentials (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  identity_id BIGINT UNSIGNED NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  password_version VARCHAR(64) NOT NULL,
  last_rotated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL,
  CONSTRAINT uq_local_credentials_identity_id UNIQUE (identity_id),
  CONSTRAINT fk_local_credentials_identity_id FOREIGN KEY (identity_id) REFERENCES identities(id)
);

CREATE TABLE IF NOT EXISTS directory_ous (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  identity_source_id BIGINT UNSIGNED NOT NULL,
  external_id VARCHAR(190) NOT NULL,
  dn VARCHAR(512) NULL,
  name VARCHAR(190) NOT NULL,
  captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_directory_ous UNIQUE (identity_source_id, external_id),
  CONSTRAINT fk_directory_ous_identity_source_id FOREIGN KEY (identity_source_id) REFERENCES identity_sources(id)
);

CREATE TABLE IF NOT EXISTS directory_users (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  identity_source_id BIGINT UNSIGNED NOT NULL,
  external_id VARCHAR(190) NOT NULL,
  -- AD/LDAP optional stable identifiers
  object_guid CHAR(36) NULL,
  object_sid VARCHAR(190) NULL,
  upn VARCHAR(255) NULL,
  dn VARCHAR(512) NULL,
  when_changed DATETIME NULL,
  usn_changed BIGINT UNSIGNED NULL,
  username VARCHAR(190) NULL,
  display_name VARCHAR(190) NOT NULL,
  email VARCHAR(255) NULL,
  snapshot_version INT UNSIGNED NOT NULL DEFAULT 1,
  snapshot_source VARCHAR(64) NULL,
  snapshot_hash CHAR(64) NULL,
  last_snapshot_at DATETIME(6) NULL,
  ou_id BIGINT UNSIGNED NULL,
  captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_directory_users UNIQUE (identity_source_id, external_id),
  CONSTRAINT uq_directory_users_object_guid UNIQUE (identity_source_id, object_guid),
  CONSTRAINT uq_directory_users_object_sid UNIQUE (identity_source_id, object_sid),
  CONSTRAINT fk_directory_users_identity_source_id FOREIGN KEY (identity_source_id) REFERENCES identity_sources(id),
  CONSTRAINT fk_directory_users_ou_id FOREIGN KEY (ou_id) REFERENCES directory_ous(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS identity_bindings (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  identity_id BIGINT UNSIGNED NOT NULL,
  directory_user_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL,
  CONSTRAINT fk_identity_bindings_identity_id FOREIGN KEY (identity_id) REFERENCES identities(id),
  CONSTRAINT fk_identity_bindings_directory_user_id FOREIGN KEY (directory_user_id) REFERENCES directory_users(id),
  CONSTRAINT uq_identity_bindings_identity_id_directory_user_id UNIQUE (identity_id, directory_user_id)
);
