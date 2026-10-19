-- ============================================================
-- BornToShare Wizard - Logging DB schema pack
-- Logging/activity schema used by production services.
-- ============================================================


CREATE TABLE IF NOT EXISTS audit_event (
  id BINARY(16) NOT NULL PRIMARY KEY,
  event_time DATETIME(6) NOT NULL,
  actor_type VARCHAR(20) NOT NULL,
  actor_id VARCHAR(255) NULL,
  action VARCHAR(128) NOT NULL,
  entity_type VARCHAR(80) NULL,
  entity_id VARCHAR(255) NULL,
  zone_id BIGINT NULL,
  root_id BIGINT NULL,
  endpoint_id BIGINT NULL,
  result VARCHAR(20) NOT NULL DEFAULT 'success',
  severity VARCHAR(20) NOT NULL DEFAULT 'info',
  correlation_id VARCHAR(128) NULL,
  source_service VARCHAR(100) NOT NULL DEFAULT 'unknown',
  metadata_json JSON NULL,
  hash_prev CHAR(64) NULL,
  hash_current CHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
