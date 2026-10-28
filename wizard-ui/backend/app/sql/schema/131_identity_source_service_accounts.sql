-- ============================================================
-- BornToShare — Service accounts per capability of an identity source
--
-- Each capability may use its own account (least privilege):
--   snapshot     : reads the directory (users, groups, memberships)
--   auth         : finds the user being authenticated (read)
--   provisioning : creates AD groups and changes their members (delegation on the zone OUs)
-- Without a row for a capability, the account of the source (identity_sources.bind_dn /
-- bind_password_ref) is used. Passwords stay in the Secret Broker (sm:// reference only).
-- ============================================================

CREATE TABLE IF NOT EXISTS identity_source_service_accounts (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  identity_source_id BIGINT UNSIGNED NOT NULL,
  purpose VARCHAR(32) NOT NULL,
  bind_dn VARCHAR(512) NOT NULL,
  bind_password_ref VARCHAR(512) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_issa_source_purpose UNIQUE (identity_source_id, purpose),
  CONSTRAINT chk_issa_purpose CHECK (purpose IN ('snapshot', 'auth', 'provisioning')),
  CONSTRAINT fk_issa_identity_source_id FOREIGN KEY (identity_source_id) REFERENCES identity_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Backfill: link AD identities to their directory user (group roles, effective access).
-- Same rule as core-service app/services/identity_bindings.py; idempotent.
INSERT INTO identity_bindings (identity_id, directory_user_id)
SELECT i.id, du.id
FROM identities i
JOIN directory_users du
  ON du.identity_source_id = i.source_id
 AND (
   LOWER(TRIM(du.external_id)) = LOWER(TRIM(i.external_id))
   OR (du.object_guid IS NOT NULL AND LOWER(du.object_guid) = LOWER(TRIM(BOTH '}' FROM TRIM(BOTH '{' FROM i.external_id))))
   OR (du.username IS NOT NULL AND LOWER(du.username) = LOWER(i.username))
 )
WHERE LOWER(COALESCE(i.auth_source, '')) = 'ad'
  AND LOWER(COALESCE(i.type, 'user')) = 'user'
ON DUPLICATE KEY UPDATE deleted_at = NULL;
