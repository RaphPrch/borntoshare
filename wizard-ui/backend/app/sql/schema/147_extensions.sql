-- Extensions (Advanced Settings › Extensions): where BornToShare sends its events (syslog, Splunk…) and the
-- Centreon check. One row per extension; its secret is in secret_items. Deliveries keep the last sends.
-- Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS extensions (
  ext_key VARCHAR(32) NOT NULL PRIMARY KEY,
  enabled TINYINT(1) NOT NULL DEFAULT 0,
  config_json TEXT NULL,
  routes_json TEXT NULL,
  secret_ref VARCHAR(255) NULL,
  updated_by VARCHAR(190) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS extension_deliveries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  ext_key VARCHAR(32) NOT NULL,
  event_type VARCHAR(32) NOT NULL,
  summary VARCHAR(255) NULL,
  status VARCHAR(16) NOT NULL,
  detail VARCHAR(500) NULL,
  attempts INT NOT NULL DEFAULT 1,
  latency_ms INT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_extension_deliveries_key_at (ext_key, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
