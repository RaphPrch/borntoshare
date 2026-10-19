-- Zone provisioning policy
-- Controls provisioning behavior and defaults for a zone.

CREATE TABLE IF NOT EXISTS zone_provisioning_policy (
  zone_id BIGINT UNSIGNED NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 0,
  policy_mode ENUM('ON_FIRST_ACCESS_REQUEST') NOT NULL DEFAULT 'ON_FIRST_ACCESS_REQUEST',
  ou_strategy VARCHAR(24) NOT NULL DEFAULT 'IDENTITY_DEFAULT', -- IDENTITY_DEFAULT|ZONE_STATIC
  static_ou_dn VARCHAR(512) NULL,
  base_ou_dn VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (zone_id),
  KEY idx_zone_policy_enabled_mode (enabled, policy_mode),
  CONSTRAINT ck_zone_policy_ou_strategy
    CHECK (ou_strategy IN ('IDENTITY_DEFAULT', 'ZONE_STATIC')),
  CONSTRAINT ck_zone_policy_zone_static_requires_static_ou
    CHECK (
      ou_strategy <> 'ZONE_STATIC'
      OR COALESCE(NULLIF(static_ou_dn, ''), NULL) IS NOT NULL
    ),
  CONSTRAINT fk_zone_policy_zone
    FOREIGN KEY (zone_id) REFERENCES zones(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
