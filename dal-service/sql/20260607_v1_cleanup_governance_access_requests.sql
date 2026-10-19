-- V1 cleanup: remove steward owners, multi-step approval history, and access-request SLA remnants.
-- Safe to run multiple times on MariaDB/MySQL.

SET time_zone = '+00:00';

DELETE FROM governance_alerts
WHERE alert_type = 'missing_steward'
   OR JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.role')) = 'steward';

DELETE FROM storage_root_roles
WHERE LOWER(role) = 'steward';

DROP VIEW IF EXISTS v_access_request_approvals;

DROP TABLE IF EXISTS approvals;

DROP INDEX IF EXISTS idx_ar_sla_status_created ON access_requests;

