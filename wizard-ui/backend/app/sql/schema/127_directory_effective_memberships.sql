-- schema/127_directory_effective_memberships.sql
-- Flattened effective memberships (snapshot-aware)

CREATE TABLE IF NOT EXISTS directory_effective_memberships (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  identity_source_id BIGINT UNSIGNED NOT NULL,
  snapshot_id BIGINT UNSIGNED NULL,
  directory_user_id BIGINT UNSIGNED NOT NULL,
  directory_group_id BIGINT UNSIGNED NOT NULL,
  depth INT NOT NULL DEFAULT 0,
  path_hash VARCHAR(128) NULL,
  resolution_type VARCHAR(32) NOT NULL DEFAULT 'direct',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT fk_dem_identity_source_id FOREIGN KEY (identity_source_id) REFERENCES identity_sources(id) ON DELETE CASCADE,
  CONSTRAINT fk_dem_snapshot_id FOREIGN KEY (snapshot_id) REFERENCES directory_snapshots(id) ON DELETE SET NULL,
  CONSTRAINT fk_dem_directory_user_id FOREIGN KEY (directory_user_id) REFERENCES directory_users(id) ON DELETE CASCADE,
  CONSTRAINT fk_dem_directory_group_id FOREIGN KEY (directory_group_id) REFERENCES directory_groups(id) ON DELETE CASCADE,

  KEY idx_dem_identity_source (identity_source_id),
  KEY idx_dem_snapshot (snapshot_id),
  KEY idx_dem_user (directory_user_id),
  KEY idx_dem_group (directory_group_id),
  KEY idx_dem_user_group (directory_user_id, directory_group_id),
  KEY idx_dem_snapshot_user (snapshot_id, directory_user_id),
  KEY idx_dem_snapshot_group (snapshot_id, directory_group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
