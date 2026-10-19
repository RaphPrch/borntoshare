-- schema/117_storage_root_roles.sql
-- Storage root governance roles (guardian only)

CREATE TABLE IF NOT EXISTS storage_root_roles (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

  root_id BIGINT UNSIGNED NOT NULL,
  identity_id BIGINT UNSIGNED NOT NULL,

  role ENUM('guardian') NOT NULL,

  assigned_by BIGINT UNSIGNED NULL,
  assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uq_root_identity_role (root_id, identity_id, role),
  KEY idx_root_roles_identity (identity_id),

  CONSTRAINT fk_root_roles_root
    FOREIGN KEY (root_id) REFERENCES storage_roots(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_root_roles_identity
    FOREIGN KEY (identity_id) REFERENCES identities(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_root_roles_assigned_by
    FOREIGN KEY (assigned_by) REFERENCES identities(id)
    ON DELETE SET NULL
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;
