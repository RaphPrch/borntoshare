-- schema/166_access_explorer.sql
-- Access Explorer: « which folders does this account or group reach » looked up by name, not by reading the ACL of
-- every folder. One row per NTFS entry of the last ACL read of a folder (storage_roots.discovered_permissions_json →
-- permissions), kept in step by the core at each read (services/root_payload.py). principal_key: the account name
-- without its domain, lower case (CORP\GG_Finance → gg_finance), as short_name() of the core.
-- Applied by the migration account. Idempotent.

CREATE TABLE IF NOT EXISTS storage_root_acl_entries (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  storage_root_id BIGINT UNSIGNED NOT NULL,
  principal VARCHAR(512) NOT NULL,
  principal_key VARCHAR(190) NOT NULL,
  raw VARCHAR(255) NULL,
  CONSTRAINT fk_srae_storage_root_id FOREIGN KEY (storage_root_id) REFERENCES storage_roots(id) ON DELETE CASCADE,
  KEY ix_srae_principal (principal_key, storage_root_id),
  KEY ix_srae_root (storage_root_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The folders read before this pack: their entries from the JSON (a folder already indexed is left as it is)
INSERT INTO storage_root_acl_entries (storage_root_id, principal, principal_key, raw)
SELECT sr.id, TRIM(jt.principal),
       LEFT(LOWER(TRIM(SUBSTRING_INDEX(REPLACE(TRIM(jt.principal), '/', '\\'), '\\', -1))), 190),
       LEFT(jt.raw, 255)
FROM storage_roots sr
JOIN JSON_TABLE(sr.discovered_permissions_json, '$.permissions[*]'
       COLUMNS (principal VARCHAR(512) PATH '$.principal', raw VARCHAR(1024) PATH '$.raw')) jt
WHERE sr.discovered_permissions_json IS NOT NULL
  AND JSON_VALID(sr.discovered_permissions_json)
  AND TRIM(COALESCE(jt.principal, '')) <> ''
  AND NOT EXISTS (SELECT 1 FROM storage_root_acl_entries e WHERE e.storage_root_id = sr.id);

-- The groups holding an account or a group (path of a nested membership, read upwards)
CREATE INDEX IF NOT EXISTS ix_dsm_member ON directory_snapshot_memberships (snapshot_id, member_external_id);
