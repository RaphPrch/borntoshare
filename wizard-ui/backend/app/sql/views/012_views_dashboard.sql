-- ============================================================
-- BornToShare — Views DASHBOARD (v4.2 minimal)
-- Depends on BASE + CONTEXT
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ============================================================
-- Expiring requests
-- ============================================================
DROP VIEW IF EXISTS v_access_requests_expiring_soon;
CREATE OR REPLACE VIEW v_access_requests_expiring_soon AS
SELECT
  ar.id AS access_request_id,
  ar.requester_identity_id AS requester_id,
  sr.id AS storage_root_id,
  sr.name AS storage_root_name,
  ari.expires_at AS expires_at,
  TIMESTAMPDIFF(HOUR, NOW(), ari.expires_at) AS hours_remaining
FROM access_requests ar
JOIN access_request_items ari ON ari.access_request_id = ar.id
LEFT JOIN storage_roots sr ON sr.id = ari.target_id
WHERE LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
  AND ari.expires_at IS NOT NULL
  AND ari.expires_at > NOW()
  AND LOWER(COALESCE(ar.status, '')) IN ('approved', 'executed');
;
;

-- ============================================================
-- Global dashboard overview (v4.2)
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_overview;
CREATE OR REPLACE VIEW v_dashboard_overview AS
SELECT
  (SELECT COUNT(*) FROM zones)             AS zones_count,
  (SELECT COUNT(*) FROM storage_endpoints) AS storage_endpoints_count,
  (SELECT COUNT(*) FROM storage_roots)     AS storage_roots_count,
  0                                                                 AS admins_count,
  (SELECT COUNT(*) FROM tags)                                       AS tags_count,
  (SELECT COUNT(*) FROM access_requests)                             AS access_requests_count,
  (SELECT COUNT(*) FROM access_requests WHERE status = 'pending')    AS pending_requests_count;
