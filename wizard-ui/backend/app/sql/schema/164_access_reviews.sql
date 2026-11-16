-- Access review campaigns: at a given time, every person who reaches a governed folder is listed for its guardians,
-- who keep or remove each access. Removing an access granted by a request revokes it (AD group membership);
-- an access that does not come from BornToShare is marked « to handle by hand ». Applied by the migration account.
-- Idempotent.

CREATE TABLE IF NOT EXISTS access_reviews (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(190) NOT NULL,
  -- open · closed
  status VARCHAR(16) NOT NULL DEFAULT 'open',
  -- JSON list of storage root ids; NULL: every governed folder at the opening
  scope_root_ids TEXT NULL,
  due_at DATETIME NULL,
  created_by_identity_id BIGINT UNSIGNED NULL,
  created_by VARCHAR(190) NULL,
  created_at DATETIME NOT NULL,
  closed_at DATETIME NULL,
  closed_by VARCHAR(190) NULL,
  KEY ix_access_reviews_status (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS access_review_items (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  review_id BIGINT UNSIGNED NOT NULL,
  storage_root_id BIGINT UNSIGNED NOT NULL,
  person_key VARCHAR(190) NOT NULL,
  username VARCHAR(190) NULL,
  display_name VARCHAR(255) NULL,
  -- read · write, as the permissions of the folder say at the opening
  level VARCHAR(16) NULL,
  -- How the person reaches the folder (request, AD group, group outside BornToShare), JSON
  via_json TEXT NULL,
  -- Requests that can be revoked to remove this access (comma separated)
  revocable_request_ids VARCHAR(500) NULL,
  -- keep · revoke (NULL: not decided yet)
  decision VARCHAR(16) NULL,
  note VARCHAR(500) NULL,
  decided_by VARCHAR(190) NULL,
  decided_at DATETIME NULL,
  -- revoked · manual (not granted by BornToShare: to remove by hand) · failed
  outcome VARCHAR(16) NULL,
  outcome_detail VARCHAR(500) NULL,
  UNIQUE KEY uq_access_review_items_person (review_id, storage_root_id, person_key),
  KEY ix_access_review_items_root (review_id, storage_root_id),
  CONSTRAINT fk_access_review_items_review FOREIGN KEY (review_id) REFERENCES access_reviews(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
