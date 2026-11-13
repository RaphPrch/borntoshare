-- Tags of the sub-folders of a governed folder (a smart policy « also on the sub-folders »: chemin:irm tags
-- DATA\Images IRM, est:mot-de-passe tags the folder that holds the files found). Path from the share, as the 5S
-- explorer and the measures keep it. Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS folder_tags (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  storage_root_id BIGINT NOT NULL,
  path VARCHAR(1024) NOT NULL,
  path_hash CHAR(40) NOT NULL,          -- SHA-1 of the lower-case path
  tag_id BIGINT NOT NULL,
  policy_id BIGINT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_folder_tags (storage_root_id, path_hash, tag_id),
  KEY ix_folder_tags_tag (tag_id),
  KEY ix_folder_tags_policy (policy_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
