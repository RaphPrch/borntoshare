DROP VIEW IF EXISTS v_storage_root_access_profile_users;
DROP VIEW IF EXISTS v_storage_root_access_profile_members;
CREATE OR REPLACE VIEW v_storage_root_access_profile_members AS
SELECT
  srap.storage_root_id AS storage_root_id,
  srap.id AS storage_root_access_profile_id,
  srap.access_profile_id AS access_profile_id,
  COALESCE(NULLIF(ap.name, ''), ap.code) AS access_profile_name,
  COALESCE(i.id, 0) AS identity_id,
  COALESCE(i.display_name, i.username, du.display_name, du.username, du.external_id) AS user_display_name,
  CAST('effective_membership' AS CHAR(64)) AS evidence_kind,
  COALESCE(ds.activated_at, ds.completed_at, ds.finished_at, ds.started_at, dem.created_at, dem.updated_at) AS snapshot_taken_at,
  CAST(dg.external_id AS CHAR(190)) AS from_group_external_id
FROM storage_root_access_profiles srap
LEFT JOIN access_profiles ap ON ap.id = srap.access_profile_id
JOIN storage_roots sr ON sr.id = srap.storage_root_id
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
JOIN directory_groups dg
  ON dg.identity_source_id = COALESCE(se.identity_source_id, dg.identity_source_id)
 AND (
      LOWER(dg.name) = LOWER(srap.group_name)
      OR LOWER(COALESCE(dg.external_id, '')) = LOWER(COALESCE(srap.group_external_id, ''))
      OR LOWER(COALESCE(dg.dn, '')) = LOWER(srap.group_name)
    )
JOIN directory_effective_memberships dem
  ON dem.directory_group_id = dg.id
 AND dem.identity_source_id = dg.identity_source_id
JOIN directory_users du ON du.id = dem.directory_user_id
LEFT JOIN identity_bindings ib
  ON ib.directory_user_id = du.id
 AND ib.deleted_at IS NULL
LEFT JOIN identities i ON i.id = ib.identity_id
LEFT JOIN directory_snapshots ds ON ds.id = dem.snapshot_id
WHERE COALESCE(ap.active, 1) = 1
  AND srap.deleted_at IS NULL
  AND dg.deleted_at IS NULL;

CREATE OR REPLACE VIEW v_storage_root_access_profile_users AS
SELECT DISTINCT
  storage_root_id,
  storage_root_access_profile_id,
  access_profile_id,
  access_profile_name,
  identity_id,
  user_display_name,
  evidence_kind,
  snapshot_taken_at,
  from_group_external_id
FROM v_storage_root_access_profile_members
WHERE identity_id > 0;
