-- ============================================================
-- BornToShare — Views DASHBOARD (v4.2 minimal)
-- Depends on BASE + CONTEXT
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ============================================================
-- Access requests counts
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_access_requests_counts;
CREATE OR REPLACE VIEW v_dashboard_access_requests_counts AS
SELECT
  ar.status AS status,
  COUNT(*) AS requests_count
FROM access_requests ar
GROUP BY ar.status;

DROP VIEW IF EXISTS v_dashboard_access_requests;
CREATE OR REPLACE VIEW v_dashboard_access_requests AS
SELECT * FROM v_dashboard_access_requests_counts;

-- ============================================================
-- User summary (v4.2 minimal)
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_user_summary;
CREATE OR REPLACE VIEW v_dashboard_user_summary AS
SELECT
  ar.requester_identity_id AS requester_identity_id,
  COUNT(*) AS total_requests,
  SUM(CASE WHEN ar.status = 'pending'  THEN 1 ELSE 0 END) AS pending_requests,
  SUM(CASE WHEN ar.status = 'approved' THEN 1 ELSE 0 END) AS approved_requests,
  SUM(CASE WHEN ar.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_requests,
  JSON_OBJECT(
    'pending',  SUM(CASE WHEN ar.status = 'pending'  THEN 1 ELSE 0 END),
    'approved', SUM(CASE WHEN ar.status = 'approved' THEN 1 ELSE 0 END),
    'rejected', SUM(CASE WHEN ar.status = 'rejected' THEN 1 ELSE 0 END)
  ) AS requests_by_status,
  COUNT(DISTINCT CASE
    WHEN LOWER(COALESCE(ar.status, '')) IN ('approved', 'executed')
      THEN ari.permission
    ELSE NULL
  END) AS access_profiles_count,
  SUM(CASE
    WHEN ari.expires_at IS NOT NULL
      AND ari.expires_at > NOW()
      AND ari.expires_at < NOW() + INTERVAL 7 DAY
      THEN 1
    ELSE 0
  END) AS expiring_requests_count,
  MIN(CASE
    WHEN ari.expires_at IS NOT NULL
      AND ari.expires_at > NOW()
      THEN TIMESTAMPDIFF(DAY, NOW(), ari.expires_at)
    ELSE NULL
  END) AS next_expiration_days
FROM access_requests ar
LEFT JOIN access_request_items ari ON ari.access_request_id = ar.id
WHERE ar.requester_identity_id IS NOT NULL
GROUP BY ar.requester_identity_id;

-- ============================================================
-- Requests by zone
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_access_requests_by_zone;
CREATE OR REPLACE VIEW v_dashboard_access_requests_by_zone AS
SELECT
  z.id   AS zone_id,
  z.name AS zone_name,
  COUNT(DISTINCT ar.id) AS requests_count,
  SUM(CASE WHEN LOWER(COALESCE(ar.status, '')) = 'pending' THEN 1 ELSE 0 END) AS pending_requests_count,
  SUM(CASE WHEN LOWER(COALESCE(ar.status, '')) = 'approved' THEN 1 ELSE 0 END) AS approved_requests_count,
  SUM(CASE WHEN LOWER(COALESCE(ar.status, '')) = 'rejected' THEN 1 ELSE 0 END) AS rejected_requests_count
FROM zones z
LEFT JOIN storage_endpoints se ON se.zone_id = z.id
LEFT JOIN storage_roots sr ON sr.storage_endpoint_id = se.id
LEFT JOIN access_request_items ari ON ari.target_type = 'storage_root' AND ari.target_id = sr.id
LEFT JOIN access_requests ar ON ar.id = ari.access_request_id
GROUP BY z.id, z.name;

-- ============================================================
-- Latest user requests
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_user_latest_requests;
CREATE OR REPLACE VIEW v_dashboard_user_latest_requests AS
SELECT
  ar.requester_identity_id AS requester_identity_id,
  ar.id AS id,
  ar.status AS status,
  ar.created_at AS created_at,
  ar.updated_at AS updated_at,
  ar.requester_identity_id AS requester_id,
  COALESCE(i.display_name, i.username, CONCAT('Identity #', ar.requester_identity_id)) AS requester_display_name,
  sr.id AS storage_root_id,
  COALESCE(sr.name, CONCAT('storage_root#', COALESCE(ari.target_id, 0))) AS storage_root_name,
  ari.permission AS requested_level,
  ari.permission AS requested_level_label,
  ari.permission AS access_profile_code
FROM access_requests ar
LEFT JOIN identities i ON i.id = ar.requester_identity_id
LEFT JOIN access_request_items ari ON ari.id = (
  SELECT x.id
  FROM access_request_items x
  WHERE x.access_request_id = ar.id
  ORDER BY x.id ASC
  LIMIT 1
)
LEFT JOIN storage_roots sr ON sr.id = ari.target_id
WHERE LOWER(COALESCE(ari.target_type, '')) = 'storage_root';

-- ============================================================
-- Effective access
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_user_effective_access;
CREATE OR REPLACE VIEW v_dashboard_user_effective_access AS
SELECT
  v.actor_id AS requester_identity_id,
  v.storage_root_id AS storage_root_id,
  v.storage_root_name AS storage_root_name,
  v.identity_source_id AS identity_source_id,
  v.directory_snapshot_id AS directory_snapshot_id,
  v.access_level AS access_level,
  v.access_level AS access_profile_code,
  v.granted_at AS granted_at,
  v.expires_at AS expires_at,
  v.actor_id AS actor_id,
  COALESCE(v.actor_display_name, i.display_name, i.username, v.actor_external_id, CONCAT('Identity #', v.actor_id)) AS actor_display_name,
  v.source AS source
FROM v_storage_root_effective_access v
LEFT JOIN identities i ON i.id = v.actor_id;

-- ============================================================
-- User dashboard overview (JSON payload)
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_user_overview;
CREATE OR REPLACE VIEW v_dashboard_user_overview AS
SELECT
  COALESCE(
    (
      SELECT JSON_OBJECTAGG(status, requests_count)
      FROM v_dashboard_access_requests_counts
    ),
    JSON_OBJECT()
  ) AS requests_by_status,
  COALESCE(
    (
      SELECT JSON_ARRAYAGG(req)
      FROM (
        SELECT JSON_OBJECT(
          'id', id,
          'requester_identity_id', requester_identity_id,
          'storage_root_name', storage_root_name,
          'requested_access', requested_level,
          'status', status,
          'created_at', created_at
        ) AS req
        FROM v_dashboard_user_latest_requests
      ) t
    ),
    JSON_ARRAY()
  ) AS latest_requests,
  COALESCE(
    (
      SELECT JSON_ARRAYAGG(acc)
      FROM (
        SELECT JSON_OBJECT(
          'requester_identity_id', requester_identity_id,
          'storage_root_id', storage_root_id,
          'storage_root_name', storage_root_name,
          'access_level', access_level,
          'access_profile_code', access_profile_code,
          'granted_at', granted_at,
          'expires_at', expires_at,
          'actor_id', actor_id,
          'actor_display_name', actor_display_name,
          'source', source
        ) AS acc
        FROM (
          SELECT
            v.actor_id AS requester_identity_id,
            v.storage_root_id AS storage_root_id,
            v.storage_root_name AS storage_root_name,
            v.identity_source_id AS identity_source_id,
            v.directory_snapshot_id AS directory_snapshot_id,
            v.access_level AS access_level,
            v.access_level AS access_profile_code,
            v.granted_at AS granted_at,
            v.expires_at AS expires_at,
            v.actor_id AS actor_id,
            COALESCE(v.actor_display_name, i.display_name, i.username, v.actor_external_id, CONCAT('Identity #', v.actor_id)) AS actor_display_name,
            v.source AS source
          FROM v_storage_root_effective_access v
          LEFT JOIN identities i ON i.id = v.actor_id
        ) effective_access
      ) t
    ),
    JSON_ARRAY()
  ) AS effective_access;

-- ============================================================
-- Activity (30 days) based on access_requests
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_access_requests_activity_30d;
CREATE OR REPLACE VIEW v_dashboard_access_requests_activity_30d AS
SELECT
  DATE(created_at) AS day,
  COUNT(*)         AS requests_count
FROM access_requests
GROUP BY DATE(created_at);

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

DROP VIEW IF EXISTS v_dashboard_access_requests_expiring_soon;
CREATE OR REPLACE VIEW v_dashboard_access_requests_expiring_soon AS
SELECT
  COUNT(*) AS expiring_requests_count,
  MIN(TIMESTAMPDIFF(DAY, NOW(), expires_at)) AS next_expiration_days
FROM v_access_requests_expiring_soon;

-- ============================================================
-- Storage roots without owner / policy (v4.2 minimal)
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_storage_roots_without_owner;
CREATE OR REPLACE VIEW v_dashboard_storage_roots_without_owner AS
SELECT
  sr.id,
  sr.name
FROM storage_roots sr
LEFT JOIN storage_root_roles srr
  ON srr.root_id = sr.id
 AND LOWER(srr.role) = 'guardian'
WHERE srr.id IS NULL;
;

DROP VIEW IF EXISTS v_dashboard_storage_roots_without_policy;
CREATE OR REPLACE VIEW v_dashboard_storage_roots_without_policy AS
SELECT
  sr.id,
  sr.name
FROM storage_roots sr
LEFT JOIN storage_root_access_profiles srap
  ON srap.storage_root_id = sr.id
WHERE srap.storage_root_id IS NULL;
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
  (SELECT COUNT(*) FROM access_profiles)                            AS access_profiles_count,
  (SELECT COUNT(*) FROM access_requests)                             AS access_requests_count,
  (SELECT COUNT(*) FROM access_requests WHERE status = 'pending')    AS pending_requests_count;

-- ============================================================
-- Storage roots stats by zone (v4.2)
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_storage_roots_stats_by_zone;
CREATE OR REPLACE VIEW v_dashboard_storage_roots_stats_by_zone AS
SELECT
  z.id   AS zone_id,
  z.name AS zone_name,
  SUM(CASE WHEN sr.status = 'active' THEN 1 ELSE 0 END) AS storage_roots_active,
  COUNT(sr.id)                                          AS storage_roots_total
FROM zones z
LEFT JOIN storage_endpoints se ON se.zone_id = z.id
LEFT JOIN storage_roots sr ON sr.storage_endpoint_id = se.id
GROUP BY z.id, z.name;

-- ============================================================
-- Requests by access profile
-- ============================================================
DROP VIEW IF EXISTS v_dashboard_access_requests_by_profile;
