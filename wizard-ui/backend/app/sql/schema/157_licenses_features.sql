-- Licenses and features: an optional module (5S…) works only when a signed license key opens it AND an
-- administrator switched it on. The key is checked offline (public key in the application); only its hash and
-- what it opens are kept. Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS licenses (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  license_id VARCHAR(64) NOT NULL,
  key_hash CHAR(64) NOT NULL,
  key_hint VARCHAR(32) NOT NULL,
  customer VARCHAR(190) NOT NULL,
  features_json LONGTEXT NOT NULL,
  limits_json LONGTEXT NULL,
  issued_on DATE NULL,
  expires_on DATE NULL,
  activated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  activated_by VARCHAR(190) NULL,
  removed_at DATETIME NULL,
  removed_by VARCHAR(190) NULL,
  UNIQUE KEY ux_licenses_hash (key_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS feature_flags (
  feature VARCHAR(64) NOT NULL PRIMARY KEY,
  enabled TINYINT(1) NOT NULL DEFAULT 0,
  settings_json LONGTEXT NULL,
  updated_by VARCHAR(190) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
