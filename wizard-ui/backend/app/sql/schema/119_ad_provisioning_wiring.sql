-- AD provisioning wiring

CREATE TABLE IF NOT EXISTS provisioning_jobs (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  correlation_id VARCHAR(128) NOT NULL,
  job_type VARCHAR(32) NOT NULL,
  action VARCHAR(64) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'QUEUED',
  storage_root_access_profile_id BIGINT UNSIGNED NULL,
  identity_source_id BIGINT UNSIGNED NULL,
  payload_json JSON NULL,
  result_json JSON NULL,
  metrics_json JSON NULL,
  error_json JSON NULL,
  error_code VARCHAR(64) NULL,
  error_message TEXT NULL,
  started_at TIMESTAMP NULL,
  finished_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_provisioning_jobs_correlation UNIQUE (correlation_id),
  CONSTRAINT fk_provisioning_jobs_srap_id FOREIGN KEY (storage_root_access_profile_id) REFERENCES storage_root_access_profiles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS governance_events (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  event_type VARCHAR(64) NOT NULL,
  target_type VARCHAR(64) NOT NULL,
  target_id BIGINT UNSIGNED NULL,
  storage_root_access_profile_id BIGINT UNSIGNED NULL,
  provisioning_job_id BIGINT UNSIGNED NULL,
  status VARCHAR(32) NULL,
  payload_json JSON NULL,
  prev_hash CHAR(64) NULL,
  event_hash CHAR(64) NOT NULL,
  actor_ip VARCHAR(64) NULL,
  user_agent VARCHAR(256) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_governance_events_srap_id FOREIGN KEY (storage_root_access_profile_id) REFERENCES storage_root_access_profiles(id) ON DELETE SET NULL,
  CONSTRAINT fk_governance_events_job_id FOREIGN KEY (provisioning_job_id) REFERENCES provisioning_jobs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- V1 strict cleanup: transient legacy provisioning tables removed.
DROP TABLE IF EXISTS ad_group_instances;
DROP TABLE IF EXISTS provisioning_groups;
