-- ============================================================
-- RBAC — SQL-first roles
--
-- IMPORTANT
-- - Compatible MySQL / MariaDB
-- - No secrets stored here
-- - Roles are the source of truth for authz
--
-- Model
-- - roles: closed set (platform_admin, user)
-- - identity_roles: grant role to identity OR to directory_group
-- ============================================================

CREATE TABLE IF NOT EXISTS roles (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(64) NOT NULL,
  label VARCHAR(255) NOT NULL,
  description TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_roles_code UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO roles (code, label, description)
VALUES
  ('user', 'User', 'Standard application access within BornToShare'),
  ('platform_admin', 'Platform administrator', 'Full administrative access within BornToShare')
ON DUPLICATE KEY UPDATE
  label = VALUES(label),
  description = VALUES(description);


CREATE TABLE IF NOT EXISTS identity_roles (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,

  -- Exactly one subject must be set
  identity_id BIGINT UNSIGNED NULL,
  directory_group_id BIGINT UNSIGNED NULL,

  role_id BIGINT UNSIGNED NOT NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'manual',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_identity_roles_identity_id
    FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE,
  CONSTRAINT fk_identity_roles_directory_group_id
    FOREIGN KEY (directory_group_id) REFERENCES directory_groups(id) ON DELETE CASCADE,
  CONSTRAINT fk_identity_roles_role_id
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE RESTRICT,

  -- MySQL 8.0+ / MariaDB 10.2+ may enforce CHECK; older versions ignore it.
  -- Keep it anyway as contractual schema documentation.
  CONSTRAINT ck_identity_roles_one_subject
    CHECK ( (identity_id IS NULL) <> (directory_group_id IS NULL) )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
