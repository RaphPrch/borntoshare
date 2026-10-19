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

-- Capsules views removed in V1 contract
