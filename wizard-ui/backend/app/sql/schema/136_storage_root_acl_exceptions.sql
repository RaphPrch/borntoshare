-- ACL entries of a storage root accepted as they are (Storage roots › Permissions › « Accept the gap »).
-- An entry added on the file server outside BornToShare stops being reported as a gap once accepted.
-- Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS storage_root_acl_exceptions (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  storage_root_id BIGINT UNSIGNED NOT NULL,
  principal VARCHAR(255) NOT NULL,          -- as read in the ACL, lower case (DOMAIN\group)
  note VARCHAR(500) NULL,
  accepted_by VARCHAR(255) NULL,
  accepted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_storage_root_acl_exception (storage_root_id, principal),
  CONSTRAINT fk_storage_root_acl_exception_root FOREIGN KEY (storage_root_id) REFERENCES storage_roots (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
