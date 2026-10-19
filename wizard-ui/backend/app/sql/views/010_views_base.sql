-- ============================================================
-- BornToShare — Views BASE (tables only)
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ============================================================
-- Zones
-- ============================================================
DROP VIEW IF EXISTS v_zones;
CREATE OR REPLACE VIEW v_zones AS
SELECT
  z.id        AS id,
  z.name      AS name,
  z.code      AS code,
  1 AS is_active,
  (SELECT COUNT(*)
     FROM storage_endpoints se
    WHERE se.zone_id = z.id
  ) AS storage_endpoints_count,

  (SELECT COUNT(*)
     FROM storage_roots sr
      JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
     WHERE se.zone_id = z.id
  ) AS storage_roots_count
FROM zones z;

-- ============================================================
-- Tags
-- ============================================================
DROP VIEW IF EXISTS v_tags;
CREATE OR REPLACE VIEW v_tags AS
SELECT
  t.id         AS id,
  t.name       AS name,
  t.name       AS label,
  t.name       AS code,
  NULL AS color_rgb,
  NULL AS value_text
FROM tags t;


-- ============================================================
-- Directory / Identity
-- ============================================================
DROP VIEW IF EXISTS v_directory_groups;
CREATE OR REPLACE VIEW v_directory_groups AS
SELECT
  g.id          AS id,
  g.identity_source_id AS domain_id,
  LOWER(COALESCE(s.type, 'unknown')) AS domain_type,
  s.name AS domain_name,

  g.name        AS name,
  g.code        AS code,
  g.external_id AS external_id,
  g.dn          AS dn,

  1            AS is_active,
  NULL         AS imported_at
FROM directory_groups g
LEFT JOIN identity_sources s ON s.id = g.identity_source_id;

DROP VIEW IF EXISTS v_identity_context;
CREATE OR REPLACE VIEW v_identity_context AS
SELECT
  i.id           AS identity_id,
  i.username     AS username,
  i.display_name AS display_name,
  i.email        AS email,
  i.auth_source  AS auth_source,
  i.is_active    AS is_active
FROM identities i;

-- ============================================================
-- Access profiles
-- ============================================================
-- v_access_profiles is defined in views/120_views_access_profiles.sql
-- to avoid duplicate definitions with conflicting columns.

-- ============================================================
-- Storage endpoints — BASE
-- (renamed to avoid collision with CONTEXT)
-- ============================================================
DROP VIEW IF EXISTS v_storage_endpoints_base;
CREATE OR REPLACE VIEW v_storage_endpoints_base AS
SELECT
  se.id,
  se.name,
  se.endpoint_type AS type,
  CASE
    WHEN COALESCE(NULLIF(TRIM(se.host), ''), NULL) IS NULL THEN NULL
    WHEN se.port IS NULL THEN se.host
    ELSE CONCAT(se.host, ':', se.port)
  END AS endpoint_target,
  se.status,

  se.created_at,
  se.updated_at
FROM storage_endpoints se;

DROP VIEW IF EXISTS v_storage_endpoints_health;
CREATE OR REPLACE VIEW v_storage_endpoints_health AS
SELECT
  se.id,
  se.name,
  se.endpoint_type AS type,
  se.status,
  se.last_probe_at AS last_probe_at,
  TIMESTAMPDIFF(SECOND, se.last_probe_at, UTC_TIMESTAMP()) AS seconds_since_last_probe
FROM storage_endpoints se;

-- Capsules views removed in V1 contract
