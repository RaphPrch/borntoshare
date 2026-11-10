-- Database b2s_fives_inventory of the 5S module: the fingerprints of the files (duplicates between folders).
-- Applied by the migration account (wizard, make deploy). Idempotent.

CREATE TABLE IF NOT EXISTS fingerprints (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  storage_root_id BIGINT NOT NULL,
  fingerprint CHAR(64) NOT NULL,
  size_bytes BIGINT UNSIGNED NOT NULL,
  path VARCHAR(1024) NOT NULL,
  modified_at DATETIME NULL,
  KEY ix_fingerprints_print (fingerprint, size_bytes),
  KEY ix_fingerprints_root (storage_root_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
