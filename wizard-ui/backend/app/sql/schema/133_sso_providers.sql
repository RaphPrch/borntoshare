-- ============================================================
-- BornToShare — SSO providers (Keycloak, OpenID Connect)
-- Advanced Settings › Infrastructure › Keycloak. Each provider is backed by an identity source of type
-- "oidc" (identities created at the first SSO sign-in belong to it).
-- ============================================================

CREATE TABLE IF NOT EXISTS sso_providers (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  identity_source_id BIGINT UNSIGNED NULL,
  name VARCHAR(120) NOT NULL,
  base_url VARCHAR(512) NOT NULL,                  -- https://sso.example.com (without /realms)
  realm VARCHAR(120) NOT NULL,
  client_id VARCHAR(190) NOT NULL,
  client_secret_ref VARCHAR(512) NULL,             -- secret broker; NULL for a public client (PKCE only)
  scopes VARCHAR(255) NOT NULL DEFAULT 'openid profile email',
  username_claim VARCHAR(64) NOT NULL DEFAULT 'preferred_username',
  roles_claim VARCHAR(190) NOT NULL DEFAULT 'realm_access.roles',   -- dotted path in the token, or "groups"
  role_mapping_json JSON NULL,                     -- [{"value": "b2s-admins", "role": "platform_admin"}, ...]
  default_role VARCHAR(64) NULL,                   -- role when nothing matches; NULL refuses the sign-in
  link_existing_identities TINYINT(1) NOT NULL DEFAULT 1,  -- same user name as an imported AD identity: that identity is used
  button_label VARCHAR(120) NULL,
  verify_tls TINYINT(1) NOT NULL DEFAULT 1,
  is_enabled TINYINT(1) NOT NULL DEFAULT 1,
  status VARCHAR(16) NOT NULL DEFAULT 'unknown',   -- unknown | healthy | down
  last_check_at DATETIME NULL,
  last_message VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_sso_providers_name UNIQUE (name),
  CONSTRAINT uq_sso_providers_realm_client UNIQUE (base_url(190), realm, client_id),
  CONSTRAINT fk_sso_providers_identity_source_id FOREIGN KEY (identity_source_id) REFERENCES identity_sources(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
