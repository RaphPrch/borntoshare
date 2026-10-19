-- ============================================================
-- BornToShare — Storage root access groups (one AD group per root and level)
-- A row is created on the first approved request for that level (READ or WRITE);
-- the group is then reused and only gets new members.
-- ============================================================

CREATE TABLE IF NOT EXISTS storage_root_access_profiles (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  storage_root_id BIGINT UNSIGNED NOT NULL,
  access_level_code VARCHAR(16) NOT NULL,          -- READ | WRITE
  group_name VARCHAR(128) NOT NULL,                -- sAMAccountName, fixed at creation
  group_external_id VARCHAR(190) NULL,             -- AD objectGUID/DN once the group exists
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING',   -- PENDING | SUCCEEDED | FAILED
  error_message TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_srap_root_level UNIQUE (storage_root_id, access_level_code),
  CONSTRAINT uq_srap_root_group_name UNIQUE (storage_root_id, group_name),
  CONSTRAINT chk_srap_level CHECK (access_level_code IN ('READ', 'WRITE')),
  CONSTRAINT fk_srap_storage_root_id FOREIGN KEY (storage_root_id) REFERENCES storage_roots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
