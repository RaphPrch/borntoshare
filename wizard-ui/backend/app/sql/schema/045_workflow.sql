-- schema/045_workflow.sql
-- Workflow layer — Requests
-- MariaDB/MySQL compatible

-- Access profiles (TEMPLATE ONLY)
CREATE TABLE IF NOT EXISTS access_profiles (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(190) NOT NULL,
  description TEXT NULL,
  permission VARCHAR(16) NOT NULL DEFAULT 'READ',
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_access_profiles_code UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS access_requests (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(32) NOT NULL,
  requester_identity_id BIGINT UNSIGNED NULL,
  status VARCHAR(32) NOT NULL,                -- pending|approved|rejected|executed|revoked
  decision_comment TEXT NULL,
  decided_at TIMESTAMP NULL,
  revoked_at TIMESTAMP NULL,
  directory_snapshot_id BIGINT UNSIGNED NULL,
  context_snapshot_at TIMESTAMP NULL,
  requested_principal_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS access_request_items (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  access_request_id BIGINT UNSIGNED NOT NULL,
  target_type VARCHAR(32) NOT NULL,
  target_id BIGINT UNSIGNED NOT NULL,
  permission VARCHAR(32) NOT NULL,
  expires_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_access_request_items_access_request_id FOREIGN KEY (access_request_id) REFERENCES access_requests(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS access_request_item_executions (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  access_request_id BIGINT UNSIGNED NOT NULL,
  access_request_item_id BIGINT UNSIGNED NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING', -- PENDING|RUNNING|DONE|FAILED
  error_message TEXT NULL,
  requested_payload_json JSON NULL,
  result_json JSON NULL,
  started_at TIMESTAMP NULL,
  finished_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_arie_access_request_id FOREIGN KEY (access_request_id) REFERENCES access_requests(id),
  CONSTRAINT fk_arie_access_request_item_id FOREIGN KEY (access_request_item_id) REFERENCES access_request_items(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
