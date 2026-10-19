-- views/141_views_workflow.sql
-- Vues UI pour écran Requests
-- IMPORTANT: requiert tables core:
-- identities (id, display_name, type, source_id, external_id)
-- storage_roots (id, name) ; zones (id, name)

SET NAMES utf8mb4;
SET time_zone = '+00:00';

DROP VIEW IF EXISTS v_access_requests;
CREATE OR REPLACE VIEW v_access_requests AS
SELECT
  ar.id AS request_id,
  ar.code AS request_code,
  ar.decision_comment AS justification,
  COALESCE(
    JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.display_name')),
    JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.username')),
    req.display_name,
    'Unknown'
  ) AS requested_for_display,
  ar.status AS status,
  ar.status AS status_label,
  ar.created_at AS created_at,
  ar.updated_at AS updated_at,
  COALESCE(ari.target_type, 'storage_root') AS scope_type,
  COALESCE(sr.name, CONCAT('/', COALESCE(ari.target_type, 'resource'), '/', COALESCE(ari.target_id, 0))) AS scope_display,
  sr.id AS storage_root_id,
  sr.storage_endpoint_id AS storage_endpoint_id,
  sr.name AS storage_root_name,
  sr.root_path AS target_path,
  COALESCE(ari.permission, 'read') AS access_profile_name,
  ari.expires_at AS expires_at,
  JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.type')) AS requested_principal_type,
  JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.dn')) AS requested_principal_dn,
  JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.external_id')) AS requested_principal_external_id,
  (
    SELECT e.status
    FROM access_request_item_executions e
    WHERE e.access_request_id = ar.id
    ORDER BY e.id DESC
    LIMIT 1
  ) AS latest_execution_status,
  (
    SELECT CAST(e.id AS CHAR(64))
    FROM access_request_item_executions e
    WHERE e.access_request_id = ar.id
    ORDER BY e.id DESC
    LIMIT 1
  ) AS latest_execution_job_id,
  0 AS impact_direct_users_count,
  0 AS impact_snapshot_users_count,
  NULL AS impact_snapshot_taken_at
FROM access_requests ar
LEFT JOIN identities req ON req.id = ar.requester_identity_id
LEFT JOIN access_request_items ari ON ari.id = (
  SELECT x.id
  FROM access_request_items x
  WHERE x.access_request_id = ar.id
  ORDER BY x.id ASC
  LIMIT 1
)
LEFT JOIN storage_roots sr ON (
  LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
  AND sr.id = ari.target_id
)
;

DROP VIEW IF EXISTS v_access_request_timeline;
CREATE OR REPLACE VIEW v_access_request_timeline AS
SELECT
  ar.id AS request_id,
  CAST('submit' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS event_type,
  CONVERT(COALESCE(req.display_name,'Unknown') USING utf8mb4) COLLATE utf8mb4_unicode_ci AS actor_display,
  CONVERT(ar.decision_comment USING utf8mb4) COLLATE utf8mb4_unicode_ci AS message,
  ar.created_at AS created_at
FROM access_requests ar
LEFT JOIN identities req ON req.id = ar.requester_identity_id
UNION ALL
SELECT
  e.access_request_id AS request_id,
  CONVERT(CASE
    WHEN UPPER(COALESCE(e.status, '')) IN ('DONE') THEN 'enforce'
    WHEN UPPER(COALESCE(e.status, '')) IN ('FAILED') THEN 'enforce_failed'
    ELSE 'provision'
  END USING utf8mb4) COLLATE utf8mb4_unicode_ci AS event_type,
  CAST('system' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS actor_display,
  CONVERT(COALESCE(e.error_message, CONCAT('execution=', COALESCE(CAST(e.id AS CHAR(64)), 'n/a'), ' status=', e.status)) USING utf8mb4) COLLATE utf8mb4_unicode_ci AS message,
  COALESCE(e.finished_at, e.started_at, e.created_at) AS created_at
FROM access_request_item_executions e;

DROP VIEW IF EXISTS v_access_request_provisioning;
CREATE OR REPLACE VIEW v_access_request_provisioning AS
SELECT
  e.id AS execution_id,
  e.access_request_id,
  e.access_request_item_id,
  e.status,
  CAST(e.id AS CHAR(64)) AS job_id,
  NULL AS poll_url,
  e.error_message,
  e.started_at,
  e.finished_at,
  e.created_at,
  e.updated_at
FROM access_request_item_executions e;
