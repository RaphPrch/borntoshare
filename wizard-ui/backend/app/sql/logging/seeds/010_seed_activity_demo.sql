-- ============================================================
-- Logging DB demo seed
-- ------------------------------------------------------------
-- Mirrors the public DEV/TEST demo dataset from sql/seeds.
-- Scope is limited to demo-* correlations and is safe to re-run.
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

START TRANSACTION;

DELETE FROM audit_event
WHERE correlation_id LIKE 'demo-%';

INSERT INTO audit_event (
  id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  hash_prev,
  hash_current
)
VALUES
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-000000000001', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 2 HOUR,
    'user',
    'U-ALICE',
    'access_request.created',
    'access_request',
    'DEMO-AR-PENDING-001',
    NULL,
    NULL,
    NULL,
    'success',
    'info',
    'demo-access-request-pending',
    'dal-service',
    JSON_OBJECT('request_code', 'DEMO-AR-PENDING-001', 'requested_level', 'read'),
    NULL,
    SHA2('demo-audit-1', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-000000000002', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 50 MINUTE,
    'user',
    'DEMO-ADMIN',
    'access_request.approved',
    'access_request',
    'DEMO-AR-APPROVED-001',
    NULL,
    NULL,
    NULL,
    'success',
    'info',
    'demo-access-request-approved',
    'governance-service',
    JSON_OBJECT('request_code', 'DEMO-AR-APPROVED-001', 'decision', 'approved'),
    SHA2('demo-audit-1', 256),
    SHA2('demo-audit-2', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-000000000003', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 90 MINUTE,
    'user',
    'DEMO-ADMIN',
    'access_request.rejected',
    'access_request',
    'DEMO-AR-REJECTED-001',
    NULL,
    NULL,
    NULL,
    'success',
    'warning',
    'demo-access-request-rejected',
    'governance-service',
    JSON_OBJECT('request_code', 'DEMO-AR-REJECTED-001', 'reason', 'disabled principal'),
    SHA2('demo-audit-2', 256),
    SHA2('demo-audit-3', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-000000000004', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 3 DAY + INTERVAL 10 MINUTE,
    'system',
    'provisioning',
    'provisioning.succeeded',
    'storage_root_access_profile',
    'B2S_FINANCE_READ',
    NULL,
    NULL,
    NULL,
    'success',
    'info',
    'demo-provisioning-succeeded',
    'governance-service',
    JSON_OBJECT('group', 'B2S_FINANCE_READ', 'operation', 'acl_apply_via_group'),
    SHA2('demo-audit-3', 256),
    SHA2('demo-audit-4', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-000000000005', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 25 MINUTE,
    'system',
    'provisioning',
    'provisioning.failed',
    'storage_root_access_profile',
    'B2S_HR_WRITE',
    NULL,
    NULL,
    NULL,
    'failure',
    'critical',
    'demo-provisioning-failed',
    'governance-service',
    JSON_OBJECT('group', 'B2S_HR_WRITE', 'error_code', 'AD_GROUP_CREATE_FAILED'),
    SHA2('demo-audit-4', 256),
    SHA2('demo-audit-5', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-000000000006', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 1 DAY,
    'user',
    'DEMO-ADMIN',
    'access_request.revoked',
    'access_request',
    'DEMO-AR-REVOKED-001',
    NULL,
    NULL,
    NULL,
    'success',
    'warning',
    'demo-access-request-revoked',
    'governance-service',
    JSON_OBJECT('request_code', 'DEMO-AR-REVOKED-001', 'operation', 'revoke'),
    SHA2('demo-audit-5', 256),
    SHA2('demo-audit-6', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-000000000007', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 10 MINUTE,
    'system',
    'directory-sync',
    'identity_source.snapshot_completed',
    'identity_source',
    'DEMO-AD',
    NULL,
    NULL,
    NULL,
    'success',
    'info',
    'demo-directory-snapshot-active',
    'dal-service',
    JSON_OBJECT('snapshot_version', 7, 'users', 4, 'groups', 9, 'memberships', 12),
    SHA2('demo-audit-6', 256),
    SHA2('demo-audit-7', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-000000000008', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 80 MINUTE,
    'user',
    'U-ALICE',
    'access_request.created',
    'access_request',
    'DEMO-AR-PENDING-002',
    NULL,
    NULL,
    NULL,
    'success',
    'info',
    'demo-access-request-pending-2',
    'dal-service',
    JSON_OBJECT('request_code', 'DEMO-AR-PENDING-002', 'requested_level', 'write', 'root_path', '/corp/engineering/builds'),
    SHA2('demo-audit-7', 256),
    SHA2('demo-audit-8', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-000000000009', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 25 MINUTE,
    'user',
    'U-CLAIRE',
    'access_request.created',
    'access_request',
    'DEMO-AR-PENDING-003',
    NULL,
    NULL,
    NULL,
    'success',
    'info',
    'demo-access-request-pending-3',
    'dal-service',
    JSON_OBJECT('request_code', 'DEMO-AR-PENDING-003', 'requested_level', 'read', 'root_path', '/corp/labs/sandbox'),
    SHA2('demo-audit-8', 256),
    SHA2('demo-audit-9', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-00000000000a', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 12 MINUTE,
    'user',
    'DEMO-ADMIN',
    'access_request.approved',
    'access_request',
    'DEMO-AR-APPROVED-002',
    NULL,
    NULL,
    NULL,
    'success',
    'info',
    'demo-access-request-approved-2',
    'governance-service',
    JSON_OBJECT('request_code', 'DEMO-AR-APPROVED-002', 'decision', 'approved'),
    SHA2('demo-audit-9', 256),
    SHA2('demo-audit-10', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-00000000000b', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 15 MINUTE,
    'user',
    'DEMO-ADMIN',
    'access_request.rejected',
    'access_request',
    'DEMO-AR-REJECTED-002',
    NULL,
    NULL,
    NULL,
    'success',
    'warning',
    'demo-access-request-rejected-2',
    'governance-service',
    JSON_OBJECT('request_code', 'DEMO-AR-REJECTED-002', 'reason', 'disabled principal'),
    SHA2('demo-audit-10', 256),
    SHA2('demo-audit-11', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-00000000000c', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 6 HOUR + INTERVAL 8 MINUTE,
    'system',
    'provisioning',
    'provisioning.succeeded',
    'storage_root_access_profile',
    'B2S_SHARED_READ',
    NULL,
    NULL,
    NULL,
    'success',
    'info',
    'demo-provisioning-succeeded-shared',
    'governance-service',
    JSON_OBJECT('group', 'B2S_SHARED_READ', 'operation', 'acl_apply_via_group'),
    SHA2('demo-audit-11', 256),
    SHA2('demo-audit-12', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-00000000000d', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 55 MINUTE,
    'system',
    'provisioning',
    'provisioning.retrying',
    'storage_root_access_profile',
    'B2S_SHARED_WRITE',
    NULL,
    NULL,
    NULL,
    'pending',
    'warning',
    'demo-provisioning-retrying-shared-write',
    'governance-service',
    JSON_OBJECT('group', 'B2S_SHARED_WRITE', 'retry_count', 2),
    SHA2('demo-audit-12', 256),
    SHA2('demo-audit-13', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-00000000000e', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 10 MINUTE,
    'system',
    'provisioning',
    'provisioning.running',
    'storage_root_access_profile',
    'B2S_LEGAL_READ',
    NULL,
    NULL,
    NULL,
    'pending',
    'info',
    'demo-provisioning-running-legal',
    'governance-service',
    JSON_OBJECT('group', 'B2S_LEGAL_READ', 'progress', 65),
    SHA2('demo-audit-13', 256),
    SHA2('demo-audit-14', 256)
  ),
  (
    UNHEX(REPLACE('10000000-0000-4000-8000-00000000000f', '-', '')),
    UTC_TIMESTAMP(6) - INTERVAL 20 MINUTE,
    'system',
    'provisioning',
    'provisioning.queued',
    'storage_root_access_profile',
    'B2S_LAB_READ',
    NULL,
    NULL,
    NULL,
    'pending',
    'warning',
    'demo-provisioning-queued-lab',
    'governance-service',
    JSON_OBJECT('group', 'B2S_LAB_READ', 'operation', 'ensure_ad_group'),
    SHA2('demo-audit-14', 256),
    SHA2('demo-audit-15', 256)
  );

INSERT INTO audit_event (
  id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  hash_prev,
  hash_current
)
SELECT
  UNHEX(LPAD(HEX(n), 32, '0')) AS id,
  UTC_TIMESTAMP(6) - INTERVAL ((200 - n) * 11) HOUR - INTERVAL (n % 47) MINUTE AS event_time,
  CASE bucket
    WHEN 0 THEN 'user'
    WHEN 1 THEN 'user'
    WHEN 2 THEN 'user'
    WHEN 3 THEN 'system'
    WHEN 4 THEN 'system'
    WHEN 5 THEN 'system'
    WHEN 6 THEN 'system'
    WHEN 7 THEN 'system'
    WHEN 8 THEN 'system'
    ELSE 'system'
  END AS actor_type,
  CASE bucket
    WHEN 0 THEN 'U-ALICE'
    WHEN 1 THEN 'DEMO-ADMIN'
    WHEN 2 THEN 'DEMO-ADMIN'
    WHEN 3 THEN 'provisioning'
    WHEN 4 THEN 'provisioning'
    WHEN 5 THEN 'scanner'
    WHEN 6 THEN 'scanner'
    WHEN 7 THEN 'directory-sync'
    WHEN 8 THEN 'directory-sync'
    ELSE 'directory-sync'
  END AS actor_id,
  CASE bucket
    WHEN 0 THEN 'access_request.created'
    WHEN 1 THEN 'access_request.approved'
    WHEN 2 THEN 'access_request.rejected'
    WHEN 3 THEN 'group.created'
    WHEN 4 THEN 'group.deleted'
    WHEN 5 THEN 'storage_root.scan_started'
    WHEN 6 THEN 'storage_root.scan_completed'
    WHEN 7 THEN 'identity_source.sync_started'
    WHEN 8 THEN 'identity_source.sync_completed'
    ELSE 'identity_source.sync_failed'
  END AS action,
  CASE bucket
    WHEN 0 THEN 'access_request'
    WHEN 1 THEN 'access_request'
    WHEN 2 THEN 'access_request'
    WHEN 3 THEN 'group'
    WHEN 4 THEN 'group'
    WHEN 5 THEN 'storage_root'
    WHEN 6 THEN 'storage_root'
    WHEN 7 THEN 'identity_source'
    WHEN 8 THEN 'identity_source'
    ELSE 'identity_source'
  END AS entity_type,
  CASE bucket
    WHEN 0 THEN CASE MOD(n, 4)
      WHEN 0 THEN 'DEMO-AR-PENDING-001'
      WHEN 1 THEN 'DEMO-AR-PENDING-002'
      WHEN 2 THEN 'DEMO-AR-PENDING-003'
      ELSE 'DEMO-AR-EXPIRED-001'
    END
    WHEN 1 THEN CASE MOD(n, 4)
      WHEN 0 THEN 'DEMO-AR-APPROVED-001'
      WHEN 1 THEN 'DEMO-AR-APPROVED-002'
      WHEN 2 THEN 'DEMO-AR-EXECUTED-001'
      ELSE 'DEMO-AR-EXECUTED-002'
    END
    WHEN 2 THEN CASE MOD(n, 3)
      WHEN 0 THEN 'DEMO-AR-REJECTED-001'
      WHEN 1 THEN 'DEMO-AR-REJECTED-002'
      ELSE 'DEMO-AR-FAILED-001'
    END
    WHEN 3 THEN CASE MOD(n, 6)
      WHEN 0 THEN 'FINANCE_RW'
      WHEN 1 THEN 'FINANCE_RO'
      WHEN 2 THEN 'RH_RW'
      WHEN 3 THEN 'RH_RO'
      WHEN 4 THEN 'IT_ADMIN'
      ELSE 'SALES_RW'
    END
    WHEN 4 THEN CASE MOD(n, 6)
      WHEN 0 THEN 'FINANCE_RO'
      WHEN 1 THEN 'RH_RO'
      WHEN 2 THEN 'IT_ADMIN'
      WHEN 3 THEN 'SALES_RW'
      WHEN 4 THEN 'LOCAL_ADMIN'
      ELSE 'LOCAL_SUPPORT'
    END
    WHEN 5 THEN CASE MOD(n, 5)
      WHEN 0 THEN '/corp/finance'
      WHEN 1 THEN '/corp/hr'
      WHEN 2 THEN '/corp/engineering'
      WHEN 3 THEN '/corp/projects/shared'
      ELSE '/corp/legal'
    END
    WHEN 6 THEN CASE MOD(n, 5)
      WHEN 0 THEN '/corp/finance'
      WHEN 1 THEN '/corp/hr'
      WHEN 2 THEN '/corp/engineering'
      WHEN 3 THEN '/corp/labs/sandbox'
      ELSE '/corp/legal'
    END
    WHEN 7 THEN CASE MOD(n, 3)
      WHEN 0 THEN 'DEMO-AD'
      WHEN 1 THEN 'DEMO-OPENLDAP'
      ELSE 'DEMO-LOCAL'
    END
    WHEN 8 THEN CASE MOD(n, 3)
      WHEN 0 THEN 'DEMO-AD'
      WHEN 1 THEN 'DEMO-OPENLDAP'
      ELSE 'DEMO-LOCAL'
    END
    ELSE CASE MOD(n, 3)
      WHEN 0 THEN 'DEMO-AD'
      WHEN 1 THEN 'DEMO-OPENLDAP'
      ELSE 'DEMO-LOCAL'
    END
  END AS entity_id,
  NULL AS zone_id,
  NULL AS root_id,
  NULL AS endpoint_id,
  CASE bucket
    WHEN 2 THEN 'success'
    WHEN 5 THEN 'pending'
    WHEN 7 THEN 'pending'
    WHEN 9 THEN 'failure'
    ELSE 'success'
  END AS result,
  CASE bucket
    WHEN 2 THEN 'warning'
    WHEN 4 THEN 'warning'
    WHEN 5 THEN 'info'
    WHEN 6 THEN 'info'
    WHEN 7 THEN 'info'
    WHEN 8 THEN 'info'
    WHEN 9 THEN 'critical'
    ELSE 'info'
  END AS severity,
  CONCAT('demo-activity-batch-', LPAD(n, 3, '0')) AS correlation_id,
  CASE bucket
    WHEN 5 THEN 'scanner-service'
    WHEN 6 THEN 'scanner-service'
    WHEN 7 THEN 'identity-service'
    WHEN 8 THEN 'identity-service'
    WHEN 9 THEN 'identity-service'
    WHEN 3 THEN 'governance-service'
    WHEN 4 THEN 'governance-service'
    ELSE 'governance-service'
  END AS source_service,
  JSON_OBJECT(
    'batch', n,
    'bucket', bucket,
    'request_code',
      CASE bucket
        WHEN 0 THEN CASE MOD(n, 4)
          WHEN 0 THEN 'DEMO-AR-PENDING-001'
          WHEN 1 THEN 'DEMO-AR-PENDING-002'
          WHEN 2 THEN 'DEMO-AR-PENDING-003'
          ELSE 'DEMO-AR-EXPIRED-001'
        END
        WHEN 1 THEN CASE MOD(n, 4)
          WHEN 0 THEN 'DEMO-AR-APPROVED-001'
          WHEN 1 THEN 'DEMO-AR-APPROVED-002'
          WHEN 2 THEN 'DEMO-AR-EXECUTED-001'
          ELSE 'DEMO-AR-EXECUTED-002'
        END
        WHEN 2 THEN CASE MOD(n, 3)
          WHEN 0 THEN 'DEMO-AR-REJECTED-001'
          WHEN 1 THEN 'DEMO-AR-REJECTED-002'
          ELSE 'DEMO-AR-FAILED-001'
        END
        ELSE NULL
      END,
    'group_code',
      CASE bucket
        WHEN 3 THEN CASE MOD(n, 6)
          WHEN 0 THEN 'FINANCE_RW'
          WHEN 1 THEN 'FINANCE_RO'
          WHEN 2 THEN 'RH_RW'
          WHEN 3 THEN 'RH_RO'
          WHEN 4 THEN 'IT_ADMIN'
          ELSE 'SALES_RW'
        END
        WHEN 4 THEN CASE MOD(n, 6)
          WHEN 0 THEN 'FINANCE_RO'
          WHEN 1 THEN 'RH_RO'
          WHEN 2 THEN 'IT_ADMIN'
          WHEN 3 THEN 'SALES_RW'
          WHEN 4 THEN 'LOCAL_ADMIN'
          ELSE 'LOCAL_SUPPORT'
        END
        ELSE NULL
      END,
    'root_path',
      CASE bucket
        WHEN 5 THEN CASE MOD(n, 5)
          WHEN 0 THEN '/corp/finance'
          WHEN 1 THEN '/corp/hr'
          WHEN 2 THEN '/corp/engineering'
          WHEN 3 THEN '/corp/projects/shared'
          ELSE '/corp/legal'
        END
        WHEN 6 THEN CASE MOD(n, 5)
          WHEN 0 THEN '/corp/finance'
          WHEN 1 THEN '/corp/hr'
          WHEN 2 THEN '/corp/engineering'
          WHEN 3 THEN '/corp/labs/sandbox'
          ELSE '/corp/legal'
        END
        ELSE NULL
      END,
    'identity_source_code',
      CASE bucket
        WHEN 7 THEN CASE MOD(n, 3)
          WHEN 0 THEN 'DEMO-AD'
          WHEN 1 THEN 'DEMO-OPENLDAP'
          ELSE 'DEMO-LOCAL'
        END
        WHEN 8 THEN CASE MOD(n, 3)
          WHEN 0 THEN 'DEMO-AD'
          WHEN 1 THEN 'DEMO-OPENLDAP'
          ELSE 'DEMO-LOCAL'
        END
        WHEN 9 THEN CASE MOD(n, 3)
          WHEN 0 THEN 'DEMO-AD'
          WHEN 1 THEN 'DEMO-OPENLDAP'
          ELSE 'DEMO-LOCAL'
        END
        ELSE NULL
      END,
    'message',
      CASE bucket
        WHEN 0 THEN 'request opened'
        WHEN 1 THEN 'request approved'
        WHEN 2 THEN 'request rejected'
        WHEN 3 THEN 'group created'
        WHEN 4 THEN 'group deleted'
        WHEN 5 THEN 'scan started'
        WHEN 6 THEN 'scan completed'
        WHEN 7 THEN 'ldap sync started'
        WHEN 8 THEN 'ldap sync completed'
        ELSE 'ldap sync failed'
      END
  ) AS metadata_json,
  SHA2(CONCAT('demo-audit-', n - 1), 256) AS hash_prev,
  SHA2(CONCAT('demo-audit-', n), 256) AS hash_current
FROM (
  WITH RECURSIVE seq AS (
    SELECT 16 AS n
    UNION ALL
    SELECT n + 1
    FROM seq
    WHERE n < 200
  )
  SELECT n, MOD(n - 16, 10) AS bucket
  FROM seq
) AS demo_events;

INSERT INTO audit_event (
  id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  hash_prev,
  hash_current
)
SELECT
  UNHEX(LPAD(HEX(200 + seq), 32, '0')) AS id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  SHA2(CONCAT('demo-audit-', 200 + seq - 1), 256) AS hash_prev,
  SHA2(CONCAT('demo-audit-', 200 + seq), 256) AS hash_current
FROM (
  WITH zone_targets AS (
    SELECT
      ROW_NUMBER() OVER (ORDER BY id) AS rn,
      id,
      name,
      code,
      description
    FROM borntoshare.zones
    WHERE code LIKE 'DEMO-%'
  ),
  zone_templates AS (
    SELECT 1 AS ord, 'zone.created' AS action, 'success' AS result, 'info' AS severity, 'system' AS actor_type, 'directory-sync' AS actor_id, 'dal-service' AS source_service
    UNION ALL SELECT 2, 'zone.updated', 'success', 'info', 'user', 'DEMO-ADMIN', 'governance-service'
    UNION ALL SELECT 3, 'zone.profile_attached', 'success', 'info', 'user', 'DEMO-ADMIN', 'governance-service'
    UNION ALL SELECT 4, 'zone.profile_detached', 'denied', 'warning', 'user', 'DEMO-ADMIN', 'governance-service'
    UNION ALL SELECT 5, 'zone.probe_rerun', 'in_progress', 'info', 'system', 'scanner', 'scanner-service'
  ),
  zone_events AS (
    SELECT
      z.rn AS target_rn,
      z.id AS zone_id,
      z.code AS target_code,
      z.name AS target_name,
      z.description AS target_description,
      t.ord,
      t.action,
      t.result,
      t.severity,
      t.actor_type,
      t.actor_id,
      t.source_service,
      UTC_TIMESTAMP(6) - INTERVAL (z.rn * 12 + t.ord) DAY - INTERVAL (z.rn * 3 + t.ord) MINUTE AS event_time,
      CONCAT('demo-zone-', z.code, '-', LPAD(t.ord, 2, '0')) AS correlation_id,
      'zone' AS entity_type,
      CAST(z.id AS CHAR) AS entity_id,
      z.id AS zone_id_fk,
      NULL AS root_id,
      NULL AS endpoint_id,
      CASE t.action
        WHEN 'zone.created' THEN JSON_OBJECT(
          'before', JSON_OBJECT('name', NULL, 'status', NULL),
          'after', JSON_OBJECT('name', z.name, 'status', 'active'),
          'updated_fields', JSON_ARRAY('name', 'status')
        )
        WHEN 'zone.updated' THEN JSON_OBJECT(
          'before', JSON_OBJECT('description', CONCAT(z.description, ' (legacy)')),
          'after', JSON_OBJECT('description', z.description),
          'updated_fields', JSON_ARRAY('description')
        )
        WHEN 'zone.profile_attached' THEN JSON_OBJECT(
          'before', JSON_OBJECT('profiles', JSON_ARRAY('READ')),
          'after', JSON_OBJECT('profiles', JSON_ARRAY('READ', 'WRITE')),
          'updated_fields', JSON_ARRAY('profiles')
        )
        WHEN 'zone.profile_detached' THEN JSON_OBJECT(
          'before', JSON_OBJECT('profiles', JSON_ARRAY('READ', 'WRITE')),
          'after', JSON_OBJECT('profiles', JSON_ARRAY('READ')),
          'updated_fields', JSON_ARRAY('profiles')
        )
        ELSE JSON_OBJECT(
          'before', JSON_OBJECT('last_probe_status', 'failed', 'last_probe_message', 'Probe failed earlier'),
          'after', JSON_OBJECT('last_probe_status', 'running', 'last_probe_message', 'Probe rerun scheduled'),
          'updated_fields', JSON_ARRAY('last_probe_status', 'last_probe_message')
        )
      END AS metadata_json
    FROM zone_targets z
    CROSS JOIN zone_templates t
  )
  SELECT
    ROW_NUMBER() OVER (ORDER BY target_rn, ord) AS seq,
    event_time,
    actor_type,
    actor_id,
    action,
    entity_type,
    entity_id,
    zone_id_fk AS zone_id,
    root_id,
    endpoint_id,
    result,
    severity,
    correlation_id,
    source_service,
    metadata_json
  FROM zone_events
) AS zone_demo_events
ORDER BY seq;

INSERT INTO audit_event (
  id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  hash_prev,
  hash_current
)
SELECT
  UNHEX(LPAD(HEX(300 + seq), 32, '0')) AS id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  SHA2(CONCAT('demo-audit-', 300 + seq - 1), 256) AS hash_prev,
  SHA2(CONCAT('demo-audit-', 300 + seq), 256) AS hash_current
FROM (
  WITH endpoint_targets AS (
    SELECT
      ROW_NUMBER() OVER (ORDER BY id) AS rn,
      id,
      zone_id,
      name,
      external_id,
      endpoint_type,
      protocol,
      host,
      port,
      base_path,
      last_probe_status,
      last_probe_message,
      status
    FROM borntoshare.storage_endpoints
    WHERE external_id LIKE 'DEMO-%'
  ),
  endpoint_templates AS (
    SELECT 1 AS ord, 'storage_endpoint.created' AS action, 'success' AS result, 'info' AS severity, 'system' AS actor_type, 'provisioning' AS actor_id, 'governance-service' AS source_service
    UNION ALL SELECT 2, 'storage_endpoint.updated', 'success', 'info', 'user', 'DEMO-ADMIN', 'governance-service'
    UNION ALL SELECT 3, 'storage_endpoint.probe', 'success', 'info', 'system', 'scanner', 'scanner-service'
    UNION ALL SELECT 4, 'validation_error', 'failure', 'critical', 'system', 'validation', 'governance-service'
  ),
  endpoint_events AS (
    SELECT
      e.rn AS target_rn,
      e.id AS endpoint_id_value,
      e.zone_id AS target_zone_id,
      e.external_id AS target_code,
      e.name AS target_name,
      t.ord,
      CASE
        WHEN t.action = 'storage_endpoint.probe' AND e.protocol = 'nfs' THEN 'test_kerberos'
        WHEN t.action = 'storage_endpoint.probe' THEN 'test_smb_ntlm'
        ELSE t.action
      END AS action,
      CASE
        WHEN t.action = 'storage_endpoint.probe' AND e.last_probe_status IN ('failed', 'warning', 'unknown') THEN 'failure'
        WHEN t.action = 'validation_error' AND e.status IN ('warning', 'maintenance') THEN 'failure'
        ELSE t.result
      END AS result,
      CASE
        WHEN t.action = 'storage_endpoint.probe' AND e.last_probe_status IN ('failed', 'warning', 'unknown') THEN 'warning'
        WHEN t.action = 'validation_error' AND e.status IN ('warning', 'maintenance') THEN 'critical'
        ELSE t.severity
      END AS severity,
      t.actor_type,
      t.actor_id,
      t.source_service,
      UTC_TIMESTAMP(6) - INTERVAL (e.rn * 10 + t.ord) DAY - INTERVAL (e.rn * 2 + t.ord) MINUTE AS event_time,
      CONCAT('demo-endpoint-', e.external_id, '-', LPAD(t.ord, 2, '0')) AS correlation_id,
      'storage_endpoint' AS entity_type,
      CAST(e.id AS CHAR) AS entity_id,
      e.zone_id AS zone_id_fk,
      NULL AS root_id,
      e.id AS endpoint_id_fk,
      CASE t.action
        WHEN 'storage_endpoint.created' THEN JSON_OBJECT(
          'before', JSON_OBJECT('name', NULL, 'status', NULL),
          'after', JSON_OBJECT('name', e.name, 'status', e.status),
          'updated_fields', JSON_ARRAY('name', 'status')
        )
        WHEN 'storage_endpoint.updated' THEN JSON_OBJECT(
          'before', JSON_OBJECT('host', CONCAT(e.host, '.legacy'), 'port', e.port),
          'after', JSON_OBJECT('host', e.host, 'port', e.port),
          'updated_fields', JSON_ARRAY('host', 'port')
        )
        WHEN 'storage_endpoint.probe' THEN JSON_OBJECT(
          'before', JSON_OBJECT('last_probe_status', 'warning', 'last_probe_message', 'Previous probe was stale'),
          'after', JSON_OBJECT('last_probe_status', e.last_probe_status, 'last_probe_message', e.last_probe_message),
          'updated_fields', JSON_ARRAY('last_probe_status', 'last_probe_message')
        )
        ELSE JSON_OBJECT(
          'before', JSON_OBJECT('status', 'warning'),
          'after', JSON_OBJECT('status', e.status),
          'updated_fields', JSON_ARRAY('status')
        )
      END AS metadata_json
    FROM endpoint_targets e
    CROSS JOIN endpoint_templates t
  )
  SELECT
    ROW_NUMBER() OVER (ORDER BY target_rn, ord) AS seq,
    event_time,
    actor_type,
    actor_id,
    action,
    entity_type,
    entity_id,
    zone_id_fk AS zone_id,
    root_id,
    endpoint_id_fk AS endpoint_id,
    result,
    severity,
    correlation_id,
    source_service,
    metadata_json
  FROM endpoint_events
) AS endpoint_demo_events
ORDER BY seq;

INSERT INTO audit_event (
  id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  hash_prev,
  hash_current
)
SELECT
  UNHEX(LPAD(HEX(400 + seq), 32, '0')) AS id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  SHA2(CONCAT('demo-audit-', 400 + seq - 1), 256) AS hash_prev,
  SHA2(CONCAT('demo-audit-', 400 + seq), 256) AS hash_current
FROM (
  WITH root_targets AS (
    SELECT
      ROW_NUMBER() OVER (ORDER BY sr.id) AS rn,
      sr.id,
      sr.storage_endpoint_id,
      se.zone_id,
      se.external_id AS endpoint_code,
      sr.name,
      sr.root_path,
      sr.normalized_root_path,
      sr.status,
      sr.last_probe_status,
      sr.last_probe_message,
      sr.needs_revalidation
    FROM borntoshare.storage_roots sr
    JOIN borntoshare.storage_endpoints se ON se.id = sr.storage_endpoint_id
    WHERE se.external_id LIKE 'DEMO-%'
  ),
  root_templates AS (
    SELECT 1 AS ord, 'storage_root.created' AS action, 'success' AS result, 'info' AS severity, 'system' AS actor_type, 'provisioning' AS actor_id, 'governance-service' AS source_service
    UNION ALL SELECT 2, 'storage_root.updated', 'success', 'info', 'user', 'DEMO-ADMIN', 'governance-service'
    UNION ALL SELECT 3, 'storage_root.owners.replaced', 'success', 'info', 'user', 'DEMO-ADMIN', 'governance-service'
    UNION ALL SELECT 4, 'storage_root.probe_rerun', 'in_progress', 'info', 'system', 'scanner', 'scanner-service'
  ),
  root_events AS (
    SELECT
      r.rn AS target_rn,
      r.id AS root_id_value,
      r.storage_endpoint_id AS target_endpoint_id,
      r.zone_id AS target_zone_id,
      r.normalized_root_path AS target_path,
      r.name AS target_name,
      r.status AS target_status,
      r.last_probe_status AS target_probe_status,
      r.last_probe_message AS target_probe_message,
      r.needs_revalidation AS target_needs_revalidation,
      t.ord,
      t.action,
      CASE
        WHEN t.action = 'storage_root.probe_rerun' AND r.last_probe_status IN ('failed', 'warning') THEN 'failure'
        ELSE t.result
      END AS result,
      CASE
        WHEN t.action = 'storage_root.probe_rerun' AND r.last_probe_status IN ('failed', 'warning') THEN 'critical'
        ELSE t.severity
      END AS severity,
      t.actor_type,
      t.actor_id,
      t.source_service,
      UTC_TIMESTAMP(6) - INTERVAL (r.rn * 4 + t.ord) DAY - INTERVAL (r.rn + t.ord) MINUTE AS event_time,
      CONCAT('demo-root-', r.id, '-', LPAD(t.ord, 2, '0')) AS correlation_id,
      'storage_root' AS entity_type,
      CAST(r.id AS CHAR) AS entity_id,
      r.zone_id AS zone_id_fk,
      r.id AS root_id_fk,
      r.storage_endpoint_id AS endpoint_id_fk,
      CASE t.action
        WHEN 'storage_root.created' THEN JSON_OBJECT(
          'before', JSON_OBJECT('owner', NULL, 'status', NULL),
          'after', JSON_OBJECT('owner', 'guardian', 'status', r.status),
          'updated_fields', JSON_ARRAY('owner', 'status')
        )
        WHEN 'storage_root.updated' THEN JSON_OBJECT(
          'before', JSON_OBJECT('status', 'maintenance', 'last_probe_status', 'failed'),
          'after', JSON_OBJECT('status', r.status, 'last_probe_status', r.last_probe_status),
          'updated_fields', JSON_ARRAY('status', 'last_probe_status')
        )
        WHEN 'storage_root.owners.replaced' THEN JSON_OBJECT(
          'before', JSON_OBJECT('owner', 'previous-owner'),
          'after', JSON_OBJECT('owner', 'current-owner'),
          'updated_fields', JSON_ARRAY('owner')
        )
        ELSE JSON_OBJECT(
          'before', JSON_OBJECT('last_probe_status', 'failed', 'last_probe_message', 'Previous scan failed'),
          'after', JSON_OBJECT('last_probe_status', r.last_probe_status, 'last_probe_message', r.last_probe_message),
          'updated_fields', JSON_ARRAY('last_probe_status', 'last_probe_message')
        )
      END AS metadata_json
    FROM root_targets r
    CROSS JOIN root_templates t
  )
  SELECT
    ROW_NUMBER() OVER (ORDER BY target_rn, ord) AS seq,
    event_time,
    actor_type,
    actor_id,
    action,
    entity_type,
    entity_id,
    zone_id_fk AS zone_id,
    root_id_fk AS root_id,
    endpoint_id_fk AS endpoint_id,
    result,
    severity,
    correlation_id,
    source_service,
    metadata_json
  FROM root_events
) AS root_demo_events
ORDER BY seq;

INSERT INTO audit_event (
  id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  hash_prev,
  hash_current
)
SELECT
  UNHEX(LPAD(HEX(800 + seq), 32, '0')) AS id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  SHA2(CONCAT('demo-audit-', 800 + seq - 1), 256) AS hash_prev,
  SHA2(CONCAT('demo-audit-', 800 + seq), 256) AS hash_current
FROM (
  WITH request_targets AS (
    SELECT
      ROW_NUMBER() OVER (ORDER BY id) AS rn,
      id,
      code,
      requester_identity_id,
      status,
      decision_comment,
      created_at,
      updated_at,
      decided_at,
      revoked_at,
      context_snapshot_at
    FROM borntoshare.access_requests
    WHERE code LIKE 'DEMO-AR-%'
  ),
  request_templates AS (
    SELECT 1 AS ord, 'access_request.created' AS action, 'success' AS result, 'info' AS severity, 'user' AS actor_type, 'requester' AS actor_id, 'dal-service' AS source_service
    UNION ALL SELECT 2, 'access_request.reviewed', 'success', 'info', 'user', 'DEMO-ADMIN', 'governance-service'
  ),
  request_events AS (
    SELECT
      r.rn AS target_rn,
      r.id AS request_id_value,
      r.code AS target_code,
      r.requester_identity_id AS target_requester,
      r.status AS target_status,
      t.ord,
      CASE
        WHEN t.ord = 1 THEN 'access_request.created'
        WHEN r.status IN ('approved', 'executed') THEN 'access_request.approved'
        WHEN r.status IN ('rejected') THEN 'access_request.rejected'
        WHEN r.status IN ('revoked', 'expired', 'failed') THEN 'access_request.failed'
        ELSE 'activity_write'
      END AS action,
      CASE
        WHEN t.ord = 1 THEN 'success'
        WHEN r.status IN ('rejected') THEN 'success'
        WHEN r.status IN ('revoked', 'expired', 'failed') THEN 'failure'
        ELSE 'success'
      END AS result,
      CASE
        WHEN t.ord = 1 THEN 'info'
        WHEN r.status IN ('rejected') THEN 'warning'
        WHEN r.status IN ('revoked', 'expired', 'failed') THEN 'critical'
        ELSE 'info'
      END AS severity,
      CASE
        WHEN t.ord = 1 THEN 'user'
        ELSE 'user'
      END AS actor_type,
      CASE
        WHEN t.ord = 1 THEN CAST(r.requester_identity_id AS CHAR)
        ELSE CAST(@identity_admin_id AS CHAR)
      END AS actor_id,
      t.source_service,
      UTC_TIMESTAMP(6) - INTERVAL (r.rn * 15 + t.ord) DAY - INTERVAL (r.rn + t.ord) MINUTE AS event_time,
      CONCAT('demo-request-', r.code, '-', LPAD(t.ord, 2, '0')) AS correlation_id,
      'access_request' AS entity_type,
      CAST(r.id AS CHAR) AS entity_id,
      NULL AS zone_id_fk,
      NULL AS root_id_fk,
      NULL AS endpoint_id_fk,
      CASE t.ord
        WHEN 1 THEN JSON_OBJECT(
          'before', JSON_OBJECT('status', NULL),
          'after', JSON_OBJECT('status', r.status, 'requested_at', r.created_at),
          'updated_fields', JSON_ARRAY('status', 'requested_at')
        )
        ELSE JSON_OBJECT(
          'before', JSON_OBJECT('status', 'pending', 'comment', 'Waiting for approver review'),
          'after', JSON_OBJECT('status', r.status, 'comment', r.decision_comment),
          'updated_fields', JSON_ARRAY('status', 'comment')
        )
      END AS metadata_json
    FROM request_targets r
    CROSS JOIN request_templates t
  )
  SELECT
    ROW_NUMBER() OVER (ORDER BY target_rn, ord) AS seq,
    event_time,
    actor_type,
    actor_id,
    action,
    entity_type,
    entity_id,
    zone_id_fk AS zone_id,
    root_id_fk AS root_id,
    endpoint_id_fk AS endpoint_id,
    result,
    severity,
    correlation_id,
    source_service,
    metadata_json
  FROM request_events
) AS request_demo_events
ORDER BY seq;

INSERT INTO audit_event (
  id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  hash_prev,
  hash_current
)
SELECT
  UNHEX(LPAD(HEX(900 + seq), 32, '0')) AS id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json,
  SHA2(CONCAT('demo-audit-', 900 + seq - 1), 256) AS hash_prev,
  SHA2(CONCAT('demo-audit-', 900 + seq), 256) AS hash_current
FROM (
  WITH source_targets AS (
    SELECT
      ROW_NUMBER() OVER (ORDER BY id) AS rn,
      id,
      external_id,
      type,
      name,
      domain_name,
      status,
      last_probe_message,
      last_snapshot_at,
      last_snapshot_version
    FROM borntoshare.identity_sources
    WHERE external_id IN ('DEMO-LOCAL', 'DEMO-AD', 'DEMO-OPENLDAP')
  ),
  source_templates AS (
    SELECT 1 AS ord, 'identity_source.created' AS action, 'success' AS result, 'info' AS severity, 'system' AS actor_type, 'directory-sync' AS actor_id, 'dal-service' AS source_service
    UNION ALL SELECT 2, 'identity_source.sync_started', 'in_progress', 'info', 'system', 'directory-sync', 'dal-service'
    UNION ALL SELECT 3, 'identity_source.sync_completed', 'success', 'info', 'system', 'directory-sync', 'dal-service'
    UNION ALL SELECT 4, 'identity_source.sync_failed', 'failure', 'critical', 'system', 'directory-sync', 'dal-service'
  ),
  source_events AS (
    SELECT
      s.rn AS target_rn,
      s.id AS source_id_value,
      s.external_id AS target_code,
      s.name AS target_name,
      t.ord,
      t.action,
      CASE
        WHEN t.action = 'identity_source.sync_failed' AND s.external_id = 'DEMO-OPENLDAP' THEN 'failure'
        WHEN t.action = 'identity_source.sync_failed' AND s.external_id = 'DEMO-LOCAL' THEN 'success'
        ELSE t.result
      END AS result,
      CASE
        WHEN t.action = 'identity_source.sync_failed' AND s.external_id = 'DEMO-OPENLDAP' THEN 'warning'
        WHEN t.action = 'identity_source.sync_failed' AND s.external_id = 'DEMO-LOCAL' THEN 'info'
        ELSE t.severity
      END AS severity,
      t.actor_type,
      t.actor_id,
      t.source_service,
      UTC_TIMESTAMP(6) - INTERVAL (s.rn * 30 + t.ord) DAY - INTERVAL (s.rn + t.ord) MINUTE AS event_time,
      CONCAT('demo-source-', s.external_id, '-', LPAD(t.ord, 2, '0')) AS correlation_id,
      'identity_source' AS entity_type,
      CAST(s.id AS CHAR) AS entity_id,
      NULL AS zone_id_fk,
      NULL AS root_id_fk,
      NULL AS endpoint_id_fk,
      CASE t.action
        WHEN 'identity_source.created' THEN JSON_OBJECT(
          'before', JSON_OBJECT('status', NULL),
          'after', JSON_OBJECT('status', s.status, 'last_snapshot_version', s.last_snapshot_version),
          'updated_fields', JSON_ARRAY('status', 'last_snapshot_version')
        )
        WHEN 'identity_source.sync_started' THEN JSON_OBJECT(
          'before', JSON_OBJECT('last_snapshot_at', NULL),
          'after', JSON_OBJECT('last_snapshot_at', s.last_snapshot_at),
          'updated_fields', JSON_ARRAY('last_snapshot_at')
        )
        WHEN 'identity_source.sync_completed' THEN JSON_OBJECT(
          'before', JSON_OBJECT('last_snapshot_version', s.last_snapshot_version - 1),
          'after', JSON_OBJECT('last_snapshot_version', s.last_snapshot_version),
          'updated_fields', JSON_ARRAY('last_snapshot_version')
        )
        ELSE JSON_OBJECT(
          'before', JSON_OBJECT('last_probe_message', 'No issues reported'),
          'after', JSON_OBJECT('last_probe_message', s.last_probe_message),
          'updated_fields', JSON_ARRAY('last_probe_message')
        )
      END AS metadata_json
    FROM source_targets s
    CROSS JOIN source_templates t
  )
  SELECT
    ROW_NUMBER() OVER (ORDER BY target_rn, ord) AS seq,
    event_time,
    actor_type,
    actor_id,
    action,
    entity_type,
    entity_id,
    zone_id_fk AS zone_id,
    root_id_fk AS root_id,
    endpoint_id_fk AS endpoint_id,
    result,
    severity,
    correlation_id,
    source_service,
    metadata_json
  FROM source_events
) AS source_demo_events
ORDER BY seq;

COMMIT;
