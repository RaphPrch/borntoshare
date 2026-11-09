-- Backup guardians: during the absence of a guardian (from starts_at to ends_at, UTC), another person validates
-- the requests of their folders, sees them and receives their notices. Nothing is copied: the right comes from this
-- row while it is in force, and ends by itself. Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS guardian_substitutes (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  identity_id BIGINT NOT NULL,
  substitute_identity_id BIGINT NOT NULL,
  starts_at DATETIME NOT NULL,
  ends_at DATETIME NOT NULL,
  reason VARCHAR(300) NULL,
  created_by VARCHAR(190) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  revoked_at DATETIME NULL,
  revoked_by VARCHAR(190) NULL,
  KEY ix_guardian_substitutes_identity (identity_id, ends_at),
  KEY ix_guardian_substitutes_substitute (substitute_identity_id, ends_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
