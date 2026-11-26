-- schema/167_indicator_history.sql
-- History of the data indicators (Insights & Recommendations › Overview › Trends): one snapshot a day of the platform
-- and of each zone (folders, coverage, volume, cold data, duplicates, secrets, quotas, alerts, exposure, servers),
-- taken by core-service during its health check. Counted with the express-search rules of Storage Roots.
-- Kept 400 days. Applied by the migration account. Idempotent.

CREATE TABLE IF NOT EXISTS data_indicator_history (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  taken_on DATE NOT NULL,
  scope_type VARCHAR(16) NOT NULL,
  scope_id BIGINT UNSIGNED NOT NULL DEFAULT 0,
  indicators JSON NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT chk_data_indicator_history_scope CHECK (scope_type IN ('platform', 'zone')),
  UNIQUE KEY uq_data_indicator_history (scope_type, scope_id, taken_on),
  KEY ix_data_indicator_history_day (taken_on)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
