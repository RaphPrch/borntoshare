-- ============================================================
-- BornToShare — Views CONTEXT (depends on BASE + tables)
-- CLEAN / V1 SAFE
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

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
  se.identity_source_id,
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
  sr.status AS status,
  sr.storage_endpoint_id AS storage_endpoint_id
FROM storage_roots sr
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
LEFT JOIN storage_roots psr ON psr.id = sr.parent_storage_root_id;

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

-- ============================================================
-- Smart policies (context)
-- ============================================================

-- Capsules views removed in V1 contract
