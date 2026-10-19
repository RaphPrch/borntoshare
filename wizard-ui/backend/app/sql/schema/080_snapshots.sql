CREATE TABLE IF NOT EXISTS directory_groups (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  identity_source_id BIGINT UNSIGNED NOT NULL,
  external_id VARCHAR(255) NOT NULL,
  dn VARCHAR(512) NULL,
  when_changed DATETIME NULL,
  usn_changed BIGINT UNSIGNED NULL,
  name VARCHAR(255) NOT NULL,
  code VARCHAR(255) NULL,
  description TEXT NULL,
  snapshot_version INT UNSIGNED NOT NULL DEFAULT 1,
  snapshot_source VARCHAR(64) NULL,
  snapshot_hash CHAR(64) NULL,
  last_snapshot_at DATETIME(6) NULL,
  captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL,
  CONSTRAINT fk_directory_groups_identity_source_id FOREIGN KEY (identity_source_id) REFERENCES identity_sources(id),
  CONSTRAINT uq_directory_groups_identity_source_id_external_id UNIQUE (identity_source_id, external_id)
);

CREATE TABLE IF NOT EXISTS directory_group_members (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  group_id BIGINT UNSIGNED NOT NULL,
  directory_user_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL,
  CONSTRAINT fk_directory_group_members_group_id FOREIGN KEY (group_id) REFERENCES directory_groups(id),
  CONSTRAINT fk_directory_group_members_directory_user_id FOREIGN KEY (directory_user_id) REFERENCES directory_users(id),
  CONSTRAINT uq_directory_group_members_group_user UNIQUE (group_id, directory_user_id)
);

CREATE TABLE IF NOT EXISTS directory_snapshots (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  identity_source_id BIGINT UNSIGNED NOT NULL,
  version INT UNSIGNED NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
  snapshot_source VARCHAR(64) NULL,
  initiated_by VARCHAR(190) NULL,
  correlation_id VARCHAR(128) NULL,
  started_at DATETIME(6) NULL,
  completed_at DATETIME(6) NULL,
  finished_at DATETIME(6) NULL,
  activated_at DATETIME(6) NULL,
  archived_at DATETIME(6) NULL,
  summary_json JSON NULL,
  error_message TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_directory_snapshots_identity_source_id FOREIGN KEY (identity_source_id) REFERENCES identity_sources(id) ON DELETE CASCADE,
  KEY idx_directory_snapshots_id_source (id, identity_source_id),
  CONSTRAINT uq_directory_snapshots_source_version UNIQUE (identity_source_id, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS directory_snapshot_users (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  snapshot_id BIGINT UNSIGNED NOT NULL,
  identity_source_id BIGINT UNSIGNED NOT NULL,
  external_id VARCHAR(255) NOT NULL,
  object_guid CHAR(36) NULL,
  object_sid VARCHAR(190) NULL,
  upn VARCHAR(255) NULL,
  dn VARCHAR(512) NULL,
  when_changed DATETIME NULL,
  usn_changed BIGINT UNSIGNED NULL,
  username VARCHAR(190) NULL,
  display_name VARCHAR(190) NULL,
  email VARCHAR(255) NULL,
  source VARCHAR(64) NULL,
  snapshot_version INT UNSIGNED NOT NULL DEFAULT 1,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_directory_snapshot_users_snapshot_source FOREIGN KEY (snapshot_id, identity_source_id)
    REFERENCES directory_snapshots(id, identity_source_id) ON DELETE CASCADE,
  CONSTRAINT uq_directory_snapshot_users_snapshot_external UNIQUE (snapshot_id, external_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS directory_snapshot_groups (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  snapshot_id BIGINT UNSIGNED NOT NULL,
  identity_source_id BIGINT UNSIGNED NOT NULL,
  external_id VARCHAR(255) NOT NULL,
  dn VARCHAR(512) NULL,
  when_changed DATETIME NULL,
  usn_changed BIGINT UNSIGNED NULL,
  name VARCHAR(255) NULL,
  code VARCHAR(255) NULL,
  description TEXT NULL,
  snapshot_version INT UNSIGNED NOT NULL DEFAULT 1,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_directory_snapshot_groups_snapshot_source FOREIGN KEY (snapshot_id, identity_source_id)
    REFERENCES directory_snapshots(id, identity_source_id) ON DELETE CASCADE,
  CONSTRAINT uq_directory_snapshot_groups_snapshot_external UNIQUE (snapshot_id, external_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS directory_snapshot_memberships (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  snapshot_id BIGINT UNSIGNED NOT NULL,
  identity_source_id BIGINT UNSIGNED NOT NULL,
  group_external_id VARCHAR(255) NOT NULL,
  member_external_id VARCHAR(255) NOT NULL,
  member_type VARCHAR(16) NOT NULL DEFAULT 'user',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_directory_snapshot_memberships_snapshot_source FOREIGN KEY (snapshot_id, identity_source_id)
    REFERENCES directory_snapshots(id, identity_source_id) ON DELETE CASCADE,
  CONSTRAINT fk_directory_snapshot_memberships_group FOREIGN KEY (snapshot_id, group_external_id)
    REFERENCES directory_snapshot_groups(snapshot_id, external_id) ON DELETE CASCADE,
  CONSTRAINT chk_directory_snapshot_memberships_member_type CHECK (member_type IN ('user', 'group')),
  CONSTRAINT uq_directory_snapshot_memberships_snapshot_group_member UNIQUE (snapshot_id, group_external_id, member_external_id, member_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
