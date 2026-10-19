-- ============================================================
-- BornToShare — Effective access read models
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';
DROP VIEW IF EXISTS v_storage_root_effective_access;
DROP VIEW IF EXISTS v_effective_access_current;

CREATE OR REPLACE VIEW v_effective_access_current AS
SELECT
  ari.target_id AS storage_root_id,
  sr.name AS storage_root_name,
  i.source_id AS identity_source_id,
  ar.directory_snapshot_id AS directory_snapshot_id,
  ar.requester_identity_id AS actor_id,
  CAST(i.external_id AS CHAR(255)) COLLATE utf8mb4_unicode_ci AS actor_external_id,
  CAST(COALESCE(i.display_name, i.username) AS CHAR(255)) COLLATE utf8mb4_unicode_ci AS actor_display_name,
  LOWER(ari.permission) AS access_level,
  ar.decided_at AS granted_at,
  ari.expires_at AS expires_at,
  CAST('request' AS CHAR(32)) AS source
FROM access_request_items ari
JOIN access_requests ar ON ar.id = ari.access_request_id
LEFT JOIN storage_roots sr ON sr.id = ari.target_id
LEFT JOIN identities i ON i.id = ar.requester_identity_id
WHERE LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
  AND LOWER(COALESCE(ar.status, '')) IN ('approved', 'executed')

UNION ALL

SELECT
  srap.storage_root_id AS storage_root_id,
  sr.name AS storage_root_name,
  dem.identity_source_id AS identity_source_id,
  dem.snapshot_id AS directory_snapshot_id,
  ib.identity_id AS actor_id,
  CAST(COALESCE(iu.external_id, du.external_id) AS CHAR(255)) COLLATE utf8mb4_unicode_ci AS actor_external_id,
  CAST(COALESCE(iu.display_name, iu.username, du.display_name, du.username, du.external_id) AS CHAR(255)) COLLATE utf8mb4_unicode_ci AS actor_display_name,
  LOWER(COALESCE(NULLIF(srap.access_level_code, ''), NULLIF(ap.code, ''), NULLIF(ap.permission, ''), 'READ')) AS access_level,
  COALESCE(ds.activated_at, ds.completed_at, ds.finished_at, ds.started_at, dem.created_at, dem.updated_at) AS granted_at,
  CAST(NULL AS DATETIME) AS expires_at,
  CAST('inherited' AS CHAR(32)) AS source
FROM storage_root_access_profiles srap
LEFT JOIN storage_roots sr ON sr.id = srap.storage_root_id
LEFT JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
LEFT JOIN access_profiles ap ON ap.id = srap.access_profile_id
JOIN directory_groups dg ON dg.external_id = srap.group_external_id
JOIN directory_effective_memberships dem
  ON dem.directory_group_id = dg.id
 AND dem.identity_source_id = dg.identity_source_id
JOIN directory_users du ON du.id = dem.directory_user_id
LEFT JOIN identity_bindings ib ON ib.directory_user_id = du.id
LEFT JOIN identities iu ON iu.id = ib.identity_id
LEFT JOIN directory_snapshots ds ON ds.id = dem.snapshot_id
WHERE COALESCE(ap.active, 1) = 1
  AND COALESCE(NULLIF(TRIM(srap.group_external_id), ''), NULL) IS NOT NULL
  AND (se.identity_source_id IS NULL OR dg.identity_source_id = se.identity_source_id);

CREATE OR REPLACE VIEW v_storage_root_effective_access AS
SELECT
  storage_root_id,
  storage_root_name,
  identity_source_id,
  directory_snapshot_id,
  actor_id,
  actor_external_id,
  actor_display_name,
  access_level,
  granted_at,
  expires_at,
  source
FROM v_effective_access_current;
