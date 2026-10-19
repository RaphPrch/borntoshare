-- ============================================================
-- BornToShare — Views CONTEXT (depends on BASE + tables)
-- CLEAN / V1 SAFE
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ============================================================
-- Zones tree
-- ============================================================
DROP VIEW IF EXISTS v_zones_tree;
CREATE OR REPLACE VIEW v_zones_tree AS
SELECT
  z.id            AS zone_id,
  z.name          AS zone_name,
  CAST(z.code AS CHAR(64)) AS zone_code,
  1               AS zone_is_active,

  (SELECT COUNT(*)
     FROM storage_endpoints se
    WHERE se.zone_id = z.id
  ) AS storage_endpoints_count,
  (SELECT COUNT(*)
     FROM storage_roots sr
     JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
    WHERE se.zone_id = z.id
  ) AS storage_roots_count
FROM zones z
;

-- ============================================================
-- Storage Endpoints context (wizard / governance)
-- ============================================================
DROP VIEW IF EXISTS v_storage_endpoints_context;
CREATE OR REPLACE VIEW v_storage_endpoints_context AS
SELECT
  se.id                    AS storage_endpoint_id,
  se.name                  AS storage_endpoint_name,
  se.endpoint_type         AS storage_endpoint_type,
  se.protocol              AS protocol,
  se.host                  AS host,
  se.port                  AS port,
  se.base_path             AS base_path,
  se.auth_type             AS auth_type,
  se.bind_dn               AS bind_dn,
  se.bind_password_ref     AS bind_password_ref,
  se.capabilities          AS capabilities,
  se.description           AS description,
  se.external_id           AS external_id,
  se.is_active             AS is_active,
  se.status                AS status,

  CASE
    WHEN COALESCE(NULLIF(TRIM(se.host), ''), NULL) IS NULL THEN '—'
    WHEN se.port IS NULL THEN se.host
    ELSE CONCAT(se.host, ':', se.port)
  END AS endpoint_target,

  se.zone_id,
  (
    SELECT COUNT(*)
    FROM storage_roots sr
    WHERE sr.storage_endpoint_id = se.id
  ) AS roots_count,
  (
    SELECT COUNT(*)
    FROM access_requests ar
    JOIN access_request_items ari ON ari.access_request_id = ar.id
    JOIN storage_roots sr ON sr.id = ari.target_id
    WHERE LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
      AND sr.storage_endpoint_id = se.id
      AND LOWER(COALESCE(ar.status, '')) = 'pending'
  ) AS pending_requests_count,

  CAST(z.code AS CHAR(64)) AS zone_code,
  COALESCE(z.name, 'Unassigned') AS zone_name,

  se.last_probe_job_id,
  se.last_probe_status,
  se.last_probe_at,
  se.last_probe_message
FROM storage_endpoints se
LEFT JOIN zones z ON z.id = se.zone_id
;

-- ============================================================
-- Storage endpoint detail (optional, future use)
-- ============================================================
DROP VIEW IF EXISTS v_storage_endpoint_detail;
CREATE OR REPLACE VIEW v_storage_endpoint_detail AS
SELECT
  se.id            AS id,
  se.name          AS name,
  se.endpoint_type AS type,
  se.protocol      AS protocol,
  se.host          AS host,
  se.port          AS port,
  se.base_path     AS base_path,
  se.auth_type     AS auth_type,
  se.bind_dn       AS bind_dn,
  se.bind_password_ref AS bind_password_ref,
  se.capabilities  AS capabilities,
  se.description   AS description,
  se.external_id   AS external_id,
  se.is_active     AS is_active,
  CASE
    WHEN COALESCE(NULLIF(TRIM(se.host), ''), NULL) IS NULL THEN NULL
    WHEN se.port IS NULL THEN se.host
    ELSE CONCAT(se.host, ':', se.port)
  END AS endpoint_target,
  se.status        AS status,
  se.last_probe_job_id AS last_probe_job_id,
  se.last_probe_status AS last_probe_status,
  se.last_probe_at AS last_probe_at,
  se.last_probe_message AS last_probe_message,

  se.zone_id,
  (
    SELECT COUNT(*)
    FROM storage_roots sr
    WHERE sr.storage_endpoint_id = se.id
  ) AS roots_count,
  (
    SELECT COUNT(*)
    FROM access_requests ar
    JOIN access_request_items ari ON ari.access_request_id = ar.id
    JOIN storage_roots sr ON sr.id = ari.target_id
    WHERE LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
      AND sr.storage_endpoint_id = se.id
      AND LOWER(COALESCE(ar.status, '')) = 'pending'
  ) AS pending_requests_count,

  CAST(z.code AS CHAR(64)) AS zone_code,
  z.name           AS zone_name,

  se.created_at,
  se.updated_at
FROM storage_endpoints se
LEFT JOIN zones z ON z.id = se.zone_id
;

-- ============================================================
-- v_storage_endpoints (contract + counts)
-- ============================================================
DROP VIEW IF EXISTS v_storage_endpoints;
CREATE OR REPLACE VIEW v_storage_endpoints AS
SELECT
  se.id        AS id,
  se.name      AS name,
  se.endpoint_type AS type,
  se.protocol  AS protocol,
  se.host      AS host,
  se.port      AS port,
  se.base_path AS base_path,
  se.auth_type AS auth_type,
  se.bind_dn   AS bind_dn,
  se.bind_password_ref AS bind_password_ref,
  se.capabilities AS capabilities,
  se.description  AS description,
  se.external_id  AS external_id,
  se.is_active    AS is_active,
  CASE
    WHEN COALESCE(NULLIF(TRIM(se.host), ''), NULL) IS NULL THEN NULL
    WHEN se.port IS NULL THEN se.host
    ELSE CONCAT(se.host, ':', se.port)
  END AS endpoint_target,
  se.status        AS status,

  se.zone_id   AS zone_id,
  CAST(z.code AS CHAR(64)) AS zone_code,
  z.name       AS zone_name,

  COUNT(sr.id) AS storage_roots_count
FROM storage_endpoints se
LEFT JOIN storage_roots sr ON sr.storage_endpoint_id = se.id
LEFT JOIN zones z ON z.id = se.zone_id
 
GROUP BY
  se.id, se.name, se.endpoint_type,
  se.protocol, se.host, se.port, se.base_path,
  se.auth_type, se.bind_dn, se.bind_password_ref,
  se.capabilities, se.description, se.external_id,
  se.is_active,
  se.status,
  se.zone_id, z.code, z.name;

-- ============================================================
-- Storage Roots context
-- ============================================================
DROP VIEW IF EXISTS v_storage_roots_context;
CREATE OR REPLACE VIEW v_storage_roots_context AS
SELECT
  sr.id             AS storage_root_id,
  sr.name           AS storage_root_name,
  sr.root_path      AS root_path,
  sr.normalized_root_path AS normalized_root_path,
  sr.parent_storage_root_id AS parent_storage_root_id,
  psr.name          AS parent_storage_root_name,
  psr.root_path     AS parent_root_path,
  COALESCE(sr.inherit_owners, 0) AS inherit_owners,
  COALESCE(sr.inherit_tags, 0) AS inherit_tags,
  COALESCE(sr.inherit_access_profiles, 0) AS inherit_access_profiles,
  sr.status = 'active' AS is_active,
  sr.status         AS storage_root_status,
  CASE
    WHEN LOWER(COALESCE(se.last_probe_status, '')) = 'success' THEN 'reachable'
    WHEN LOWER(COALESCE(se.last_probe_status, '')) = 'running' THEN 'checking'
    WHEN LOWER(COALESCE(se.last_probe_status, '')) = 'failed' THEN 'unreachable'
    ELSE 'unknown'
  END AS effective_availability,
  (
    SELECT COUNT(*)
    FROM access_request_items ari
    JOIN access_requests ar ON ar.id = ari.access_request_id
    WHERE LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
      AND ari.target_id = sr.id
      AND LOWER(COALESCE(ar.status, '')) = 'pending'
  ) AS pending_validation_count,
  'storage_root' AS resource_type,
  sr.root_path     AS locator,
  sr.created_at    AS created_at,
  sr.last_probe_status AS last_probe_status,
  sr.last_probe_at AS last_probe_at,
  sr.last_probe_message AS last_probe_message,
  sr.last_discovery_at AS last_discovery_at,
  sr.last_discovery_at AS last_scan_at,
  sr.discovered_permissions_json AS discovered_permissions_json,
  sr.discovered_permissions_json AS discovered_permissions,

  se.id             AS storage_endpoint_id,
  se.name           AS storage_endpoint_name,
  se.endpoint_type  AS storage_endpoint_type,
  se.host           AS storage_endpoint_host,
  se.port           AS storage_endpoint_port,
  se.status         AS storage_endpoint_status,
  se.base_path      AS storage_endpoint_base_path,
  se.protocol       AS storage_endpoint_protocol,
  se.auth_type      AS storage_endpoint_auth_type,
  se.bind_dn        AS storage_endpoint_bind_dn,
  se.bind_password_ref AS storage_endpoint_bind_password_ref,
  se.is_active      AS storage_endpoint_is_active,
  se.last_probe_job_id AS storage_endpoint_last_probe_job_id,
  se.last_probe_status AS storage_endpoint_last_probe_status,
  se.last_probe_at AS storage_endpoint_last_probe_at,
  se.last_probe_message AS storage_endpoint_last_probe_message,

  se.zone_id        AS zone_id,
  z.name            AS zone_name
FROM storage_roots sr
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
LEFT JOIN zones z          ON z.id = se.zone_id
LEFT JOIN storage_roots psr ON psr.id = sr.parent_storage_root_id
;

-- ============================================================
-- Storage root tags
-- ============================================================
DROP VIEW IF EXISTS v_storage_root_tags;
CREATE OR REPLACE VIEW v_storage_root_tags AS
SELECT
  srt.storage_root_id AS storage_root_id,
  t.id                AS tag_id,
  t.name              AS tag_label,
  t.name              AS tag_code,
  NULL                AS tag_color
FROM storage_root_tags srt
JOIN tags t ON t.id = srt.tag_id
;

-- ============================================================
-- Storage root owners (KEEP ONE VERSION)
-- ============================================================
DROP VIEW IF EXISTS v_storage_root_owners;
CREATE OR REPLACE VIEW v_storage_root_owners AS
SELECT
  srr.root_id         AS storage_root_id,
  srr.identity_id     AS actor_id,
  i.username          AS username,
  i.display_name      AS display_name,
  i.email             AS email,
  i.type              AS identity_type,
  LOWER(srr.role)     AS role
FROM storage_root_roles srr
JOIN identities i ON i.id = srr.identity_id
WHERE LOWER(srr.role) = 'guardian'
;

-- Legacy access-profile mapping view retired from the active contract.

-- ============================================================
-- Storage root overview (context + owners + tags JSON)
-- ============================================================
DROP VIEW IF EXISTS v_storage_root_overview;
-- Retired: active DAL reads v_storage_roots_context directly.

-- ============================================================
-- Access request governance
-- ============================================================
DROP VIEW IF EXISTS v_access_request_governance;
-- Retired governance helper view.

-- ============================================================
-- Access request overview (depends on BASE views)
-- - v_access_requests_status
-- - v_access_request_last_validation
-- ============================================================
DROP VIEW IF EXISTS v_access_request_overview;
-- Retired overview helper view.

-- ============================================================
-- Access requests overview (V1 contract projection)
-- ============================================================
DROP VIEW IF EXISTS v_access_requests_overview;
-- Retired V1 projection; active list uses v_access_requests.

-- ============================================================
-- Storage roots overview (V1 contract projection)
-- ============================================================
DROP VIEW IF EXISTS v_storage_roots_overview;
-- Retired V1 projection; active list uses v_storage_roots_context.

-- ============================================================
-- Storage root access views
-- ============================================================
DROP VIEW IF EXISTS v_storage_root_access_profiles;
CREATE OR REPLACE VIEW v_storage_root_access_profiles AS
SELECT
  srap.storage_root_id AS storage_root_id,
  ap.id AS access_profile_id,
  ap.code AS access_profile_code,
  ap.name AS access_profile_name,
  UPPER(COALESCE(ap.permission, 'READ')) AS access_level,
  CAST(1 AS UNSIGNED) AS is_active,
  CAST(1 AS UNSIGNED) AS is_local
FROM storage_root_access_profiles srap
JOIN access_profiles ap ON ap.id = srap.access_profile_id;

DROP VIEW IF EXISTS v_storage_root_discovered_access;
CREATE OR REPLACE VIEW v_storage_root_discovered_access AS
SELECT
  sr.id AS storage_root_id,
  ar.requester_identity_id AS actor_id,
  LOWER(COALESCE(ari.permission, 'read')) AS access_level,
  sr.last_discovery_at AS discovered_at,
  COALESCE(
    ari.permission,
    LEFT(
      COALESCE(
        JSON_UNQUOTE(JSON_EXTRACT(sr.discovered_permissions_json, '$.permissions')),
        JSON_UNQUOTE(JSON_EXTRACT(sr.discovered_permissions_json, '$')),
        ''
      ),
      255
    )
  ) AS evidence,
  CAST(
    CASE
      WHEN LOWER(COALESCE(ar.status, '')) IN ('approved', 'executed') THEN 1.00
      WHEN LOWER(COALESCE(ar.status, '')) = 'pending' THEN 0.60
      ELSE 0.25
    END AS DECIMAL(5,2)
  ) AS confidence
FROM storage_roots sr
LEFT JOIN access_request_items ari ON ari.target_id = sr.id
  AND LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
LEFT JOIN access_requests ar ON ar.id = ari.access_request_id
WHERE sr.last_discovery_at IS NOT NULL;

-- ============================================================
-- Effective access volume (dashboard)
-- ============================================================
-- Retired dashboard helper view.

-- ============================================================
-- Console read-model helpers (zone / endpoint / root / profile)
-- ============================================================

DROP VIEW IF EXISTS v_zone_console_endpoints;
CREATE OR REPLACE VIEW v_zone_console_endpoints AS
SELECT
  se.zone_id AS zone_id,
  se.id AS id,
  se.name AS name,
  se.endpoint_type AS endpoint_type,
  se.host AS host,
  se.port AS port,
  se.status AS status,
  se.last_probe_status AS last_probe_status,
  se.last_probe_at AS last_probe_at,
  se.last_probe_message AS last_probe_message,
  se.bind_dn AS bind_dn,
  se.bind_password_ref AS bind_password_ref,
  se.bind_dn AS auth_username,
  se.bind_password_ref AS auth_secret_ref,
  CAST(COALESCE(se.is_active, 1) AS UNSIGNED) AS is_active
FROM storage_endpoints se;

DROP VIEW IF EXISTS v_zone_console_roots;
CREATE OR REPLACE VIEW v_zone_console_roots AS
SELECT
  se.zone_id AS zone_id,
  sr.id AS id,
  sr.name AS name,
  sr.root_path AS root_path,
  sr.normalized_root_path AS normalized_root_path,
  sr.parent_storage_root_id AS parent_storage_root_id,
  psr.name AS parent_storage_root_name,
  psr.root_path AS parent_root_path,
  COALESCE(sr.inherit_owners, 0) AS inherit_owners,
  COALESCE(sr.inherit_tags, 0) AS inherit_tags,
  COALESCE(sr.inherit_access_profiles, 0) AS inherit_access_profiles,
  sr.status AS status,
  sr.storage_endpoint_id AS storage_endpoint_id
FROM storage_roots sr
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
LEFT JOIN storage_roots psr ON psr.id = sr.parent_storage_root_id;

DROP VIEW IF EXISTS v_zone_console_access_profiles;

DROP VIEW IF EXISTS v_storage_endpoint_console_roots;
CREATE OR REPLACE VIEW v_storage_endpoint_console_roots AS
SELECT
  sr.storage_endpoint_id AS storage_endpoint_id,
  sr.id AS id,
  sr.name AS name,
  sr.status AS status,
  se.zone_id AS zone_id,
  z.name AS zone_name
FROM storage_roots sr
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
LEFT JOIN zones z ON z.id = se.zone_id;

DROP VIEW IF EXISTS v_storage_root_console_access_profiles;
CREATE OR REPLACE VIEW v_storage_root_console_access_profiles AS
SELECT
  srap.storage_root_id AS storage_root_id,
  ap.id AS access_profile_id,
  ap.code AS code,
  ap.name AS name,
  UPPER(COALESCE(NULLIF(srap.access_level_code, ''), NULLIF(ap.code, ''), NULLIF(ap.permission, ''), 'READ')) AS access_level_code,
  ap.permission AS permission
FROM storage_root_access_profiles srap
JOIN access_profiles ap ON ap.id = srap.access_profile_id
WHERE srap.deleted_at IS NULL;

DROP VIEW IF EXISTS v_storage_root_console_role_counts;
CREATE OR REPLACE VIEW v_storage_root_console_role_counts AS
SELECT
  srr.root_id AS storage_root_id,
  LOWER(srr.role) AS role,
  COUNT(*) AS count
FROM storage_root_roles srr
WHERE LOWER(srr.role) = 'guardian'
GROUP BY srr.root_id, LOWER(srr.role);

-- ============================================================
-- Smart policies (context)
-- ============================================================

-- Capsules views removed in V1 contract
