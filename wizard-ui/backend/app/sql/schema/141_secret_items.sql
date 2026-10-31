-- Secrets of the secret broker, encrypted with AES-256-GCM. The key (B2S_SECRET_MASTER_KEY) is never in the database.
-- The reference is authenticated with each value: a value copied to another row cannot be decrypted.
-- Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS secret_items (
  ref VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL PRIMARY KEY,
  name VARCHAR(512) NULL,
  iv VARCHAR(32) NOT NULL,
  ciphertext TEXT NOT NULL,
  key_id VARCHAR(64) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
