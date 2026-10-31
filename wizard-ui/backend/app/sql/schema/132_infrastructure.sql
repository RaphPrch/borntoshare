-- ============================================================
-- BornToShare — Infrastructure (Advanced Settings › Infrastructure)
-- Workers reached through their HTTPS agent, monitored components and their state,
-- schedules of the health check and of the data sync (executed by the workers).
-- The database connection itself lives in a runtime file read by core-service at startup
-- (it cannot be stored in the database it describes).
-- ============================================================

-- Workers (capsule-runner): agent URL and credentials (password in the secret broker)
CREATE TABLE IF NOT EXISTS infra_workers (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  host VARCHAR(255) NOT NULL,
  port INT NOT NULL DEFAULT 8443,
  use_tls TINYINT(1) NOT NULL DEFAULT 1,
  verify_tls TINYINT(1) NOT NULL DEFAULT 1,
  is_enabled TINYINT(1) NOT NULL DEFAULT 1,
  status VARCHAR(16) NOT NULL DEFAULT 'unknown',   -- unknown | healthy | degraded | down
  last_check_at DATETIME NULL,
  last_seen_at DATETIME NULL,
  last_message VARCHAR(512) NULL,
  version VARCHAR(64) NULL,
  hostname VARCHAR(255) NULL,
  max_scope VARCHAR(16) NULL,
  details_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_infra_workers_name UNIQUE (name),
  CONSTRAINT uq_infra_workers_endpoint UNIQUE (host, port),
  CONSTRAINT chk_infra_workers_status CHECK (status IN ('unknown', 'healthy', 'degraded', 'down')),
  CONSTRAINT chk_infra_workers_port CHECK (port BETWEEN 1 AND 65535)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Monitored components the health check probes from a worker (built-in platform services + custom ones)
CREATE TABLE IF NOT EXISTS infra_services (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  component_key VARCHAR(64) NOT NULL,
  label VARCHAR(120) NOT NULL,
  category VARCHAR(32) NOT NULL DEFAULT 'service',  -- web | service | data | queue | security | custom
  check_kind VARCHAR(8) NOT NULL DEFAULT 'http',    -- http | tcp
  target VARCHAR(512) NOT NULL,                     -- URL (http) or host:port (tcp)
  is_builtin TINYINT(1) NOT NULL DEFAULT 0,
  is_enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_infra_services_key UNIQUE (component_key),
  CONSTRAINT chk_infra_services_kind CHECK (check_kind IN ('http', 'tcp'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO infra_services (component_key, label, category, check_kind, target, is_builtin) VALUES
  ('web', 'Web interface', 'web', 'http', 'http://frontend-service:3000/login', 1),
  ('auth', 'Authentication service', 'service', 'http', 'http://auth-service:8000/health', 1),
  ('core', 'Core service', 'service', 'http', 'http://core-service:8000/health', 1),
  ('redis', 'Job queue (Redis)', 'queue', 'tcp', 'redis:6379', 1);

-- Last known state of every component (one row each), written by the health check
CREATE TABLE IF NOT EXISTS infra_component_status (
  component VARCHAR(96) PRIMARY KEY,               -- web, database, worker:3, identity_source:5, ...
  label VARCHAR(190) NOT NULL,
  category VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL,                     -- healthy | degraded | down | unknown
  latency_ms INT NULL,
  message VARCHAR(512) NULL,
  checked_by VARCHAR(120) NULL,                    -- core-service, or the worker that ran the check
  details_json JSON NULL,
  checked_at DATETIME NOT NULL,
  CONSTRAINT chk_infra_component_status CHECK (status IN ('healthy', 'degraded', 'down', 'unknown'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- History for the availability bars (kept 7 days)
CREATE TABLE IF NOT EXISTS infra_check_history (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  component VARCHAR(96) NOT NULL,
  status VARCHAR(16) NOT NULL,
  latency_ms INT NULL,
  checked_at DATETIME NOT NULL,
  KEY idx_infra_check_history_component (component, checked_at),
  KEY idx_infra_check_history_checked_at (checked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Regular tasks run through the workers
CREATE TABLE IF NOT EXISTS infra_schedules (
  task VARCHAR(32) PRIMARY KEY,                    -- health_check | data_sync | access_expiry (135)
  is_enabled TINYINT(1) NOT NULL DEFAULT 1,
  interval_minutes INT NOT NULL,
  options_json JSON NULL,                          -- data_sync: {"snapshots": true, "shares": true, "acl_drift": true}
  last_run_at DATETIME NULL,
  next_run_at DATETIME NULL,
  last_status VARCHAR(16) NULL,                    -- running | success | partial | failed
  last_message VARCHAR(512) NULL,
  last_summary_json JSON NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT chk_infra_schedules_task CHECK (task IN ('health_check', 'data_sync')),
  CONSTRAINT chk_infra_schedules_interval CHECK (interval_minutes BETWEEN 1 AND 10080)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- First data sync one interval after the installation, not all at once at the first start
INSERT IGNORE INTO infra_schedules (task, is_enabled, interval_minutes, options_json, next_run_at) VALUES
  ('health_check', 1, 5, NULL, NULL),
  ('data_sync', 1, 360, JSON_OBJECT('snapshots', TRUE, 'shares', TRUE, 'acl_drift', TRUE), UTC_TIMESTAMP() + INTERVAL 360 MINUTE);
