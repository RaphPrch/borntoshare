CREATE TABLE IF NOT EXISTS zone_access_profiles (
  zone_id BIGINT UNSIGNED NOT NULL,
  access_profile_id BIGINT UNSIGNED NOT NULL,
  is_active TINYINT(1) DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (zone_id, access_profile_id),
  CONSTRAINT fk_zone_access_profiles_zone_id FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE CASCADE,
  CONSTRAINT fk_zone_access_profiles_access_profile_id FOREIGN KEY (access_profile_id) REFERENCES access_profiles(id) ON DELETE CASCADE,
  KEY idx_zap_zone (zone_id),
  KEY idx_zap_profile (access_profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
