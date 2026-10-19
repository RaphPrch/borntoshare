-- ============================================================
-- BornToShare DEV/TEST demo seed
-- ------------------------------------------------------------
-- Coherent dataset for current canonical tables and runtime views.
-- Scope is limited to DEMO-* records and is safe to re-run.
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

START TRANSACTION;

-- ------------------------------------------------------------
-- Cleanup previous demo rows, dependency-first.
-- ------------------------------------------------------------

DELETE FROM governance_events
WHERE event_hash IN (
  SHA2('demo-governance-submit', 256),
  SHA2('demo-governance-approve', 256),
  SHA2('demo-governance-provision-ok', 256),
  SHA2('demo-governance-provision-failed', 256),
  SHA2('demo-governance-revoke', 256),
  SHA2('demo-governance-submit-2', 256),
  SHA2('demo-governance-provision-ok-2', 256),
  SHA2('demo-governance-running-legal', 256)
);

DELETE FROM governance_health_events
WHERE correlation_id LIKE 'demo-%';

DELETE FROM governance_alerts
WHERE alert_key LIKE 'demo.%';

DELETE FROM provisioning_jobs
WHERE correlation_id LIKE 'demo-%';

DELETE arie
FROM access_request_item_executions arie
JOIN access_requests ar ON ar.id = arie.access_request_id
WHERE ar.code LIKE 'DEMO-AR-%';

DELETE ari
FROM access_request_items ari
JOIN access_requests ar ON ar.id = ari.access_request_id
WHERE ar.code LIKE 'DEMO-AR-%';

DELETE FROM access_requests
WHERE code LIKE 'DEMO-AR-%';

DELETE srr
FROM storage_root_roles srr
JOIN storage_roots sr ON sr.id = srr.root_id
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
WHERE se.external_id LIKE 'DEMO-%';

DELETE srap
FROM storage_root_access_profiles srap
JOIN storage_roots sr ON sr.id = srap.storage_root_id
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
WHERE se.external_id LIKE 'DEMO-%';

DELETE srt
FROM storage_root_tags srt
JOIN storage_roots sr ON sr.id = srt.storage_root_id
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
WHERE se.external_id LIKE 'DEMO-%';

DELETE npo
FROM naming_policy_overrides npo
LEFT JOIN zones z ON npo.scope_type = 'zone' AND z.id = npo.scope_id
LEFT JOIN storage_endpoints se ON npo.scope_type = 'storage_endpoint' AND se.id = npo.scope_id
LEFT JOIN storage_roots sr ON npo.scope_type = 'storage_root' AND sr.id = npo.scope_id
LEFT JOIN storage_endpoints ser ON npo.scope_type = 'storage_root' AND ser.id = sr.storage_endpoint_id
WHERE z.code LIKE 'DEMO-%'
   OR se.external_id LIKE 'DEMO-%'
   OR ser.external_id LIKE 'DEMO-%';

DELETE zpp
FROM zone_provisioning_policy zpp
JOIN zones z ON z.id = zpp.zone_id
WHERE z.code LIKE 'DEMO-%';

DELETE FROM storage_roots
WHERE parent_storage_root_id IS NOT NULL
  AND storage_endpoint_id IN (
    SELECT id
    FROM storage_endpoints
    WHERE external_id LIKE 'DEMO-%'
  );

DELETE FROM storage_roots
WHERE storage_endpoint_id IN (
  SELECT id
  FROM storage_endpoints
  WHERE external_id LIKE 'DEMO-%'
);

DELETE FROM storage_endpoints
WHERE external_id LIKE 'DEMO-%';

DELETE FROM zones
WHERE code LIKE 'DEMO-%';

DELETE FROM tags
WHERE name IN (
  'Demo Critical',
  'Demo PII',
  'Demo Finance',
  'Demo HR',
  'Demo Engineering',
  'Demo Legal',
  'Demo Shared',
  'Demo Sandbox'
);

DELETE ir
FROM identity_roles ir
LEFT JOIN identities i ON i.id = ir.identity_id
LEFT JOIN directory_groups dg ON dg.id = ir.directory_group_id
LEFT JOIN identity_sources src_i ON src_i.id = i.source_id
LEFT JOIN identity_sources src_g ON src_g.id = dg.identity_source_id
WHERE src_i.external_id IN ('DEMO-LOCAL', 'DEMO-AD')
   OR src_g.external_id IN ('DEMO-LOCAL', 'DEMO-AD');

DELETE dem
FROM directory_effective_memberships dem
JOIN identity_sources src ON src.id = dem.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE ib
FROM identity_bindings ib
JOIN directory_users du ON du.id = ib.directory_user_id
JOIN identity_sources src ON src.id = du.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE dgm
FROM directory_group_members dgm
JOIN directory_groups dg ON dg.id = dgm.group_id
JOIN identity_sources src ON src.id = dg.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE dsm
FROM directory_snapshot_memberships dsm
JOIN directory_snapshots ds ON ds.id = dsm.snapshot_id
JOIN identity_sources src ON src.id = ds.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE dsu
FROM directory_snapshot_users dsu
JOIN directory_snapshots ds ON ds.id = dsu.snapshot_id
JOIN identity_sources src ON src.id = ds.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE dsg
FROM directory_snapshot_groups dsg
JOIN directory_snapshots ds ON ds.id = dsg.snapshot_id
JOIN identity_sources src ON src.id = ds.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE ds
FROM directory_snapshots ds
JOIN identity_sources src ON src.id = ds.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE du
FROM directory_users du
JOIN identity_sources src ON src.id = du.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE dg
FROM directory_groups dg
JOIN identity_sources src ON src.id = dg.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE dou
FROM directory_ous dou
JOIN identity_sources src ON src.id = dou.identity_source_id
WHERE src.external_id = 'DEMO-AD';

DELETE lc
FROM local_credentials lc
JOIN identities i ON i.id = lc.identity_id
JOIN identity_sources src ON src.id = i.source_id
WHERE src.external_id IN ('DEMO-LOCAL', 'DEMO-AD', 'DEMO-OPENLDAP');

DELETE i
FROM identities i
JOIN identity_sources src ON src.id = i.source_id
WHERE src.external_id IN ('DEMO-LOCAL', 'DEMO-AD', 'DEMO-OPENLDAP');

DELETE FROM identity_sources
WHERE external_id IN ('DEMO-LOCAL', 'DEMO-AD', 'DEMO-OPENLDAP');

-- ------------------------------------------------------------
-- Platform settings and reference dimensions.
-- ------------------------------------------------------------

INSERT INTO advanced_settings_config (id, payload_json)
VALUES (
  1,
  JSON_OBJECT(
    'demo_seed', true,
    'request_guardrails', JSON_OBJECT('block_duplicate_pending', true, 'block_existing_read', true),
    'storage_root_revalidation_days', 30
  )
)
ON DUPLICATE KEY UPDATE
  payload_json = VALUES(payload_json);

INSERT INTO naming_policy_global (
  id,
  group_prefix,
  template,
  normalize_uppercase,
  max_sam_length,
  replace_map_json,
  rootcode_strategy
)
VALUES (
  1,
  'B2S',
  '{PREFIX}_{ROOTCODE}_{PERM}',
  1,
  64,
  JSON_OBJECT(' ', '_', '-', '_'),
  'BASENAME'
)
ON DUPLICATE KEY UPDATE
  group_prefix = VALUES(group_prefix),
  template = VALUES(template),
  normalize_uppercase = VALUES(normalize_uppercase),
  max_sam_length = VALUES(max_sam_length),
  replace_map_json = VALUES(replace_map_json),
  rootcode_strategy = VALUES(rootcode_strategy);

INSERT INTO identity_sources (
  type,
  name,
  domain_name,
  protocol,
  host,
  port,
  base_dn,
  bind_dn,
  bind_password_ref,
  default_group_ou_dn,
  capabilities,
  write_enabled,
  auth_enabled,
  auth_priority,
  is_active,
  external_id,
  status,
  last_probe_at,
  last_probe_message,
  last_snapshot_at,
  last_snapshot_version,
  last_usn_changed,
  snapshot_mode,
  delta_supported,
  dirsync_supported
)
VALUES
  (
    'local',
    'Demo Local',
    'local.demo',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    JSON_OBJECT(
      'password_auth', true,
      'snapshot_enabled', true,
      'description', 'Local demo identity store for BornToShare administrators'
    ),
    0,
    1,
    10,
    1,
    'DEMO-LOCAL',
    'active',
    UTC_TIMESTAMP() - INTERVAL 2 HOUR,
    'Demo local source ready',
    UTC_TIMESTAMP() - INTERVAL 2 HOUR,
    1,
    120,
    'full',
    0,
    0
  ),
  (
    'active_directory',
    'Demo Active Directory',
    'corp.demo',
    'ldap',
    'ad01.corp.demo',
    636,
    'DC=corp,DC=demo',
    'CN=svc-borntoshare,OU=Service Accounts,DC=corp,DC=demo',
    'secret://demo/ad-bind',
    'OU=BornToShare,OU=Groups,DC=corp,DC=demo',
    JSON_OBJECT(
      'users', true,
      'groups', true,
      'write_groups', true,
      'dirsync', true,
      'description', 'Primary corporate directory used for realistic provisioning and ACL discovery'
    ),
    1,
    1,
    20,
    1,
    'DEMO-AD',
    'active',
    UTC_TIMESTAMP() - INTERVAL 15 MINUTE,
    'Demo LDAP probe succeeded',
    UTC_TIMESTAMP() - INTERVAL 10 MINUTE,
    7,
    490102,
    'delta',
    1,
    1
  ),
  (
    'openldap',
    'Demo OpenLDAP',
    'ldap.demo',
    'ldap',
    'ldap01.corp.demo',
    389,
    'dc=ldap,dc=demo',
    'cn=svc-borntoshare,ou=svc,dc=ldap,dc=demo',
    'secret://demo/openldap-bind',
    'ou=groups,dc=ldap,dc=demo',
    JSON_OBJECT(
      'users', true,
      'groups', true,
      'snapshot_enabled', true,
      'description', 'Standalone OpenLDAP demo directory used for browse and snapshot validation'
    ),
    0,
    0,
    30,
    1,
    'DEMO-OPENLDAP',
    'active',
    UTC_TIMESTAMP() - INTERVAL 30 MINUTE,
    'Demo OpenLDAP source ready',
    UTC_TIMESTAMP() - INTERVAL 30 MINUTE,
    1,
    88,
    'full',
    0,
    0
  );

SET @demo_local_source_id := (SELECT id FROM identity_sources WHERE external_id = 'DEMO-LOCAL' ORDER BY id DESC LIMIT 1);
SET @demo_ad_source_id := (SELECT id FROM identity_sources WHERE external_id = 'DEMO-AD' ORDER BY id DESC LIMIT 1);
SET @demo_openldap_source_id := (SELECT id FROM identity_sources WHERE external_id = 'DEMO-OPENLDAP' ORDER BY id DESC LIMIT 1);
SET @role_user_id := (SELECT id FROM roles WHERE code = 'user' LIMIT 1);
SET @role_admin_id := (SELECT id FROM roles WHERE code = 'platform_admin' LIMIT 1);

INSERT INTO identities (
  source_id,
  username,
  type,
  external_id,
  display_name,
  email,
  auth_source,
  is_active,
  snapshot_version,
  snapshot_source,
  provisioning_source,
  snapshot_hash,
  last_snapshot_at,
  status
)
VALUES
  (@demo_local_source_id, 'demo.admin', 'user', 'DEMO-ADMIN', 'Demo Platform Admin', 'admin@corp.demo', 'local', 1, 1, 'seed', 'explicit', SHA2('DEMO-ADMIN', 256), UTC_TIMESTAMP() - INTERVAL 2 DAY, 'active'),
  (@demo_local_source_id, 'demo.support', 'user', 'DEMO-SUPPORT', 'Demo Support', 'support@corp.demo', 'local', 1, 1, 'seed', 'explicit', SHA2('DEMO-SUPPORT', 256), UTC_TIMESTAMP() - INTERVAL 2 HOUR, 'active'),
  (@demo_ad_source_id, 'alice.finance', 'user', 'U-ALICE', 'Alice Finance', 'alice.finance@corp.demo', 'external', 1, 7, 'active_directory', 'snapshot', SHA2('U-ALICE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE, 'active'),
  (@demo_ad_source_id, 'bob.hr', 'user', 'U-BOB', 'Bob HR', 'bob.hr@corp.demo', 'external', 1, 7, 'active_directory', 'snapshot', SHA2('U-BOB', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE, 'active'),
  (@demo_ad_source_id, 'claire.audit', 'user', 'U-CLAIRE', 'Claire Auditor', 'claire.audit@corp.demo', 'external', 1, 7, 'active_directory', 'snapshot', SHA2('U-CLAIRE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE, 'active'),
  (@demo_ad_source_id, 'diego.contractor', 'user', 'U-DIEGO', 'Diego Contractor', 'diego.contractor@corp.demo', 'external', 0, 7, 'active_directory', 'snapshot', SHA2('U-DIEGO', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE, 'disabled'),
  (@demo_openldap_source_id, 'jdupont', 'user', 'U-JDUPONT', 'Jean Dupont', 'jdupont@ldap.demo', 'external', 1, 1, 'openldap', 'snapshot', SHA2('U-JDUPONT', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 'active'),
  (@demo_openldap_source_id, 'mmartin', 'user', 'U-MMARTIN', 'Marie Martin', 'mmartin@ldap.demo', 'external', 1, 1, 'openldap', 'snapshot', SHA2('U-MMARTIN', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 'active'),
  (@demo_openldap_source_id, 'pbernard', 'user', 'U-PBERNARD', 'Paul Bernard', 'pbernard@ldap.demo', 'external', 1, 1, 'openldap', 'snapshot', SHA2('U-PBERNARD', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 'active'),
  (@demo_openldap_source_id, 'clefevre', 'user', 'U-CLEFEVRE', 'Claire Lefevre', 'clefevre@ldap.demo', 'external', 1, 1, 'openldap', 'snapshot', SHA2('U-CLEFEVRE', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 'active'),
  (@demo_openldap_source_id, 'arobert', 'user', 'U-AROBERT', 'Alex Robert', 'arobert@ldap.demo', 'external', 1, 1, 'openldap', 'snapshot', SHA2('U-AROBERT', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 'active');

SET @identity_admin_id := (SELECT id FROM identities WHERE source_id = @demo_local_source_id AND external_id = 'DEMO-ADMIN' LIMIT 1);
SET @identity_support_id := (SELECT id FROM identities WHERE source_id = @demo_local_source_id AND external_id = 'DEMO-SUPPORT' LIMIT 1);
SET @identity_alice_id := (SELECT id FROM identities WHERE source_id = @demo_ad_source_id AND external_id = 'U-ALICE' LIMIT 1);
SET @identity_bob_id := (SELECT id FROM identities WHERE source_id = @demo_ad_source_id AND external_id = 'U-BOB' LIMIT 1);
SET @identity_claire_id := (SELECT id FROM identities WHERE source_id = @demo_ad_source_id AND external_id = 'U-CLAIRE' LIMIT 1);
SET @identity_diego_id := (SELECT id FROM identities WHERE source_id = @demo_ad_source_id AND external_id = 'U-DIEGO' LIMIT 1);
SET @identity_jdupont_id := (SELECT id FROM identities WHERE source_id = @demo_openldap_source_id AND external_id = 'U-JDUPONT' LIMIT 1);
SET @identity_mmartin_id := (SELECT id FROM identities WHERE source_id = @demo_openldap_source_id AND external_id = 'U-MMARTIN' LIMIT 1);
SET @identity_pbernard_id := (SELECT id FROM identities WHERE source_id = @demo_openldap_source_id AND external_id = 'U-PBERNARD' LIMIT 1);
SET @identity_clefevre_id := (SELECT id FROM identities WHERE source_id = @demo_openldap_source_id AND external_id = 'U-CLEFEVRE' LIMIT 1);
SET @identity_arobert_id := (SELECT id FROM identities WHERE source_id = @demo_openldap_source_id AND external_id = 'U-AROBERT' LIMIT 1);

INSERT INTO local_credentials (identity_id, password_hash, password_version, last_rotated_at)
VALUES (
  @identity_admin_id,
  '$argon2id$v=19$m=65536,t=3,p=4$demo$not-a-real-password-hash',
  'demo-v1',
  UTC_TIMESTAMP() - INTERVAL 5 DAY
), (
  @identity_support_id,
  '$argon2id$v=19$m=65536,t=3,p=4$demo$not-a-real-password-hash',
  'demo-v1',
  UTC_TIMESTAMP() - INTERVAL 1 DAY
)
ON DUPLICATE KEY UPDATE
  password_hash = VALUES(password_hash),
  password_version = VALUES(password_version),
  last_rotated_at = VALUES(last_rotated_at);

-- ------------------------------------------------------------
-- Directory model, current snapshot and effective memberships.
-- ------------------------------------------------------------

INSERT INTO directory_ous (identity_source_id, external_id, dn, name)
VALUES
  (@demo_ad_source_id, 'OU-FINANCE', 'OU=Finance,DC=corp,DC=demo', 'Finance'),
  (@demo_ad_source_id, 'OU-HR', 'OU=HR,DC=corp,DC=demo', 'HR'),
  (@demo_ad_source_id, 'OU-IT', 'OU=IT,DC=corp,DC=demo', 'IT');

SET @ou_finance_id := (SELECT id FROM directory_ous WHERE identity_source_id = @demo_ad_source_id AND external_id = 'OU-FINANCE' LIMIT 1);
SET @ou_hr_id := (SELECT id FROM directory_ous WHERE identity_source_id = @demo_ad_source_id AND external_id = 'OU-HR' LIMIT 1);
SET @ou_it_id := (SELECT id FROM directory_ous WHERE identity_source_id = @demo_ad_source_id AND external_id = 'OU-IT' LIMIT 1);

INSERT INTO directory_users (
  identity_source_id,
  external_id,
  object_guid,
  object_sid,
  upn,
  dn,
  when_changed,
  usn_changed,
  username,
  display_name,
  email,
  snapshot_version,
  snapshot_source,
  snapshot_hash,
  last_snapshot_at,
  ou_id
)
VALUES
  (@demo_ad_source_id, 'U-ALICE', '11111111-1111-4111-8111-111111111111', 'S-1-5-21-1000-1000-1000-1101', 'alice.finance@corp.demo', 'CN=Alice Finance,OU=Finance,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 20 MINUTE, 490001, 'alice.finance', 'Alice Finance', 'alice.finance@corp.demo', 7, 'active_directory', SHA2('U-ALICE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE, @ou_finance_id),
  (@demo_ad_source_id, 'U-BOB', '22222222-2222-4222-8222-222222222222', 'S-1-5-21-1000-1000-1000-1102', 'bob.hr@corp.demo', 'CN=Bob HR,OU=HR,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 19 MINUTE, 490002, 'bob.hr', 'Bob HR', 'bob.hr@corp.demo', 7, 'active_directory', SHA2('U-BOB', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE, @ou_hr_id),
  (@demo_ad_source_id, 'U-CLAIRE', '33333333-3333-4333-8333-333333333333', 'S-1-5-21-1000-1000-1000-1103', 'claire.audit@corp.demo', 'CN=Claire Auditor,OU=IT,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 18 MINUTE, 490003, 'claire.audit', 'Claire Auditor', 'claire.audit@corp.demo', 7, 'active_directory', SHA2('U-CLAIRE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE, @ou_it_id),
  (@demo_ad_source_id, 'U-DIEGO', '44444444-4444-4444-8444-444444444444', 'S-1-5-21-1000-1000-1000-1104', 'diego.contractor@corp.demo', 'CN=Diego Contractor,OU=Finance,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 17 MINUTE, 490004, 'diego.contractor', 'Diego Contractor', 'diego.contractor@corp.demo', 7, 'active_directory', SHA2('U-DIEGO', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE, @ou_finance_id);

SET @du_alice_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_ad_source_id AND external_id = 'U-ALICE' LIMIT 1);
SET @du_bob_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_ad_source_id AND external_id = 'U-BOB' LIMIT 1);
SET @du_claire_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_ad_source_id AND external_id = 'U-CLAIRE' LIMIT 1);
SET @du_diego_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_ad_source_id AND external_id = 'U-DIEGO' LIMIT 1);

INSERT INTO identity_bindings (identity_id, directory_user_id)
VALUES
  (@identity_alice_id, @du_alice_id),
  (@identity_bob_id, @du_bob_id),
  (@identity_claire_id, @du_claire_id),
  (@identity_diego_id, @du_diego_id);

INSERT INTO directory_groups (
  identity_source_id,
  external_id,
  dn,
  when_changed,
  usn_changed,
  name,
  code,
  description,
  snapshot_version,
  snapshot_source,
  snapshot_hash,
  last_snapshot_at
)
VALUES
  (@demo_ad_source_id, 'G-B2S-FINANCE-READ', 'CN=B2S_FINANCE_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490101, 'B2S_FINANCE_READ', 'B2S_FINANCE_READ', 'Read access to Finance root', 7, 'active_directory', SHA2('G-B2S-FINANCE-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-FINANCE-WRITE', 'CN=B2S_FINANCE_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490102, 'B2S_FINANCE_WRITE', 'B2S_FINANCE_WRITE', 'Write access to Finance root', 7, 'active_directory', SHA2('G-B2S-FINANCE-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-HR-READ', 'CN=B2S_HR_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490103, 'B2S_HR_READ', 'B2S_HR_READ', 'Read access to HR root', 7, 'active_directory', SHA2('G-B2S-HR-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-ADMINS', 'CN=B2S_PLATFORM_ADMINS,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490104, 'B2S_PLATFORM_ADMINS', 'B2S_PLATFORM_ADMINS', 'Platform administrators synced from AD', 7, 'active_directory', SHA2('G-B2S-ADMINS', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-ENG-READ', 'CN=B2S_ENG_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490105, 'B2S_ENG_READ', 'B2S_ENG_READ', 'Read access to Engineering root', 7, 'active_directory', SHA2('G-B2S-ENG-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-ENG-WRITE', 'CN=B2S_ENG_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490106, 'B2S_ENG_WRITE', 'B2S_ENG_WRITE', 'Write access to Engineering root', 7, 'active_directory', SHA2('G-B2S-ENG-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-LEGAL-READ', 'CN=B2S_LEGAL_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490107, 'B2S_LEGAL_READ', 'B2S_LEGAL_READ', 'Read access to Legal root', 7, 'active_directory', SHA2('G-B2S-LEGAL-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-SHARED-READ', 'CN=B2S_SHARED_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490108, 'B2S_SHARED_READ', 'B2S_SHARED_READ', 'Read access to Shared Projects root', 7, 'active_directory', SHA2('G-B2S-SHARED-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-SHARED-WRITE', 'CN=B2S_SHARED_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490109, 'B2S_SHARED_WRITE', 'B2S_SHARED_WRITE', 'Write access to Shared Projects root', 7, 'active_directory', SHA2('G-B2S-SHARED-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-HR-WRITE', 'CN=B2S_HR_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490110, 'B2S_HR_WRITE', 'B2S_HR_WRITE', 'Write access to HR root', 7, 'active_directory', SHA2('G-B2S-HR-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-LEGAL-WRITE', 'CN=B2S_LEGAL_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490111, 'B2S_LEGAL_WRITE', 'B2S_LEGAL_WRITE', 'Write access to Legal root', 7, 'active_directory', SHA2('G-B2S-LEGAL-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-SALES-READ', 'CN=B2S_SALES_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490112, 'B2S_SALES_READ', 'B2S_SALES_READ', 'Read access to Sales roots', 7, 'active_directory', SHA2('G-B2S-SALES-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-SALES-WRITE', 'CN=B2S_SALES_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490113, 'B2S_SALES_WRITE', 'B2S_SALES_WRITE', 'Write access to Sales roots', 7, 'active_directory', SHA2('G-B2S-SALES-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-OPS-READ', 'CN=B2S_OPS_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490114, 'B2S_OPS_READ', 'B2S_OPS_READ', 'Read access to Operations roots', 7, 'active_directory', SHA2('G-B2S-OPS-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-OPS-WRITE', 'CN=B2S_OPS_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490115, 'B2S_OPS_WRITE', 'B2S_OPS_WRITE', 'Write access to Operations roots', 7, 'active_directory', SHA2('G-B2S-OPS-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-SANDBOX-READ', 'CN=B2S_SANDBOX_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490116, 'B2S_SANDBOX_READ', 'B2S_SANDBOX_READ', 'Read access to Sandbox roots', 7, 'active_directory', SHA2('G-B2S-SANDBOX-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-SANDBOX-WRITE', 'CN=B2S_SANDBOX_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490117, 'B2S_SANDBOX_WRITE', 'B2S_SANDBOX_WRITE', 'Write access to Sandbox roots', 7, 'active_directory', SHA2('G-B2S-SANDBOX-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-COMPLIANCE-READ', 'CN=B2S_COMPLIANCE_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490118, 'B2S_COMPLIANCE_READ', 'B2S_COMPLIANCE_READ', 'Read access to Compliance roots', 7, 'active_directory', SHA2('G-B2S-COMPLIANCE-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-COMPLIANCE-WRITE', 'CN=B2S_COMPLIANCE_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490119, 'B2S_COMPLIANCE_WRITE', 'B2S_COMPLIANCE_WRITE', 'Write access to Compliance roots', 7, 'active_directory', SHA2('G-B2S-COMPLIANCE-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-ARCHIVE-READ', 'CN=B2S_ARCHIVE_READ,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490120, 'B2S_ARCHIVE_READ', 'B2S_ARCHIVE_READ', 'Read access to Archive roots', 7, 'active_directory', SHA2('G-B2S-ARCHIVE-READ', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE),
  (@demo_ad_source_id, 'G-B2S-ARCHIVE-WRITE', 'CN=B2S_ARCHIVE_WRITE,OU=BornToShare,OU=Groups,DC=corp,DC=demo', UTC_TIMESTAMP() - INTERVAL 16 MINUTE, 490121, 'B2S_ARCHIVE_WRITE', 'B2S_ARCHIVE_WRITE', 'Write access to Archive roots', 7, 'active_directory', SHA2('G-B2S-ARCHIVE-WRITE', 256), UTC_TIMESTAMP() - INTERVAL 10 MINUTE);

SET @dg_fin_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-FINANCE-READ' LIMIT 1);
SET @dg_fin_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-FINANCE-WRITE' LIMIT 1);
SET @dg_hr_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-HR-READ' LIMIT 1);
SET @dg_admins_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-ADMINS' LIMIT 1);
SET @dg_eng_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-ENG-READ' LIMIT 1);
SET @dg_eng_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-ENG-WRITE' LIMIT 1);
SET @dg_legal_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-LEGAL-READ' LIMIT 1);
SET @dg_shared_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-SHARED-READ' LIMIT 1);
SET @dg_shared_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-SHARED-WRITE' LIMIT 1);
SET @dg_hr_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-HR-WRITE' LIMIT 1);
SET @dg_legal_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-LEGAL-WRITE' LIMIT 1);
SET @dg_sales_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-SALES-READ' LIMIT 1);
SET @dg_sales_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-SALES-WRITE' LIMIT 1);
SET @dg_ops_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-OPS-READ' LIMIT 1);
SET @dg_ops_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-OPS-WRITE' LIMIT 1);
SET @dg_sandbox_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-SANDBOX-READ' LIMIT 1);
SET @dg_sandbox_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-SANDBOX-WRITE' LIMIT 1);
SET @dg_compliance_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-COMPLIANCE-READ' LIMIT 1);
SET @dg_compliance_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-COMPLIANCE-WRITE' LIMIT 1);
SET @dg_archive_read_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-ARCHIVE-READ' LIMIT 1);
SET @dg_archive_write_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_ad_source_id AND external_id = 'G-B2S-ARCHIVE-WRITE' LIMIT 1);

INSERT INTO directory_group_members (group_id, directory_user_id)
VALUES
  (@dg_fin_read_id, @du_alice_id),
  (@dg_fin_read_id, @du_claire_id),
  (@dg_fin_write_id, @du_alice_id),
  (@dg_hr_read_id, @du_bob_id),
  (@dg_admins_id, @du_claire_id),
  (@dg_eng_read_id, @du_alice_id),
  (@dg_eng_read_id, @du_claire_id),
  (@dg_eng_write_id, @du_claire_id),
  (@dg_legal_read_id, @du_bob_id),
  (@dg_shared_read_id, @du_bob_id),
  (@dg_shared_read_id, @du_claire_id),
  (@dg_shared_write_id, @du_alice_id),
  (@dg_hr_write_id, @du_bob_id),
  (@dg_hr_write_id, @du_claire_id),
  (@dg_legal_write_id, @du_claire_id),
  (@dg_sales_read_id, @du_alice_id),
  (@dg_sales_read_id, @du_claire_id),
  (@dg_sales_write_id, @du_alice_id),
  (@dg_ops_read_id, @du_bob_id),
  (@dg_ops_read_id, @du_claire_id),
  (@dg_ops_write_id, @du_claire_id),
  (@dg_sandbox_read_id, @du_diego_id),
  (@dg_sandbox_read_id, @du_claire_id),
  (@dg_sandbox_write_id, @du_claire_id),
  (@dg_compliance_read_id, @du_bob_id),
  (@dg_compliance_read_id, @du_claire_id),
  (@dg_compliance_write_id, @du_claire_id),
  (@dg_archive_read_id, @du_alice_id),
  (@dg_archive_read_id, @du_bob_id),
  (@dg_archive_write_id, @du_alice_id),
  (@dg_archive_write_id, @du_claire_id);

INSERT INTO identity_roles (identity_id, directory_group_id, role_id, source)
VALUES
  (@identity_admin_id, NULL, @role_admin_id, 'seed'),
  (NULL, @dg_admins_id, @role_admin_id, 'directory_group'),
  (@identity_alice_id, NULL, @role_user_id, 'seed'),
  (@identity_bob_id, NULL, @role_user_id, 'seed'),
  (@identity_claire_id, NULL, @role_user_id, 'seed');

INSERT INTO directory_snapshots (
  identity_source_id,
  version,
  status,
  snapshot_source,
  initiated_by,
  correlation_id,
  started_at,
  completed_at,
  finished_at,
  activated_at,
  summary_json
)
VALUES (
  @demo_ad_source_id,
    7,
    'ACTIVE',
    'active_directory',
  'demo-seed',
  'demo-directory-snapshot-active',
  UTC_TIMESTAMP(6) - INTERVAL 12 MINUTE,
  UTC_TIMESTAMP(6) - INTERVAL 10 MINUTE,
  UTC_TIMESTAMP(6) - INTERVAL 10 MINUTE,
  UTC_TIMESTAMP(6) - INTERVAL 9 MINUTE,
    JSON_OBJECT('users', 4, 'groups', 21, 'memberships', 31, 'mode', 'delta')
  );

SET @snapshot_active_id := (SELECT id FROM directory_snapshots WHERE identity_source_id = @demo_ad_source_id AND version = 7 LIMIT 1);

INSERT INTO directory_snapshot_users (
  snapshot_id,
  identity_source_id,
  external_id,
  object_guid,
  object_sid,
  upn,
  dn,
  when_changed,
  usn_changed,
  username,
  display_name,
  email,
  source,
  snapshot_version,
  is_active
)
SELECT
  @snapshot_active_id,
  identity_source_id,
  external_id,
  object_guid,
  object_sid,
  upn,
  dn,
  when_changed,
  usn_changed,
  username,
  display_name,
  email,
  'seed',
  snapshot_version,
  CASE WHEN external_id = 'U-DIEGO' THEN 0 ELSE 1 END
FROM directory_users
WHERE identity_source_id = @demo_ad_source_id;

INSERT INTO directory_snapshot_groups (
  snapshot_id,
  identity_source_id,
  external_id,
  dn,
  when_changed,
  usn_changed,
  name,
  code,
  description,
  snapshot_version,
  is_active
)
SELECT
  @snapshot_active_id,
  identity_source_id,
  external_id,
  dn,
  when_changed,
  usn_changed,
  name,
  code,
  description,
  snapshot_version,
  1
FROM directory_groups
WHERE identity_source_id = @demo_ad_source_id;

INSERT INTO directory_snapshot_memberships (
  snapshot_id,
  identity_source_id,
  group_external_id,
  member_external_id,
  member_type
)
VALUES
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-FINANCE-READ', 'U-ALICE', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-FINANCE-READ', 'U-CLAIRE', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-FINANCE-WRITE', 'U-ALICE', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-HR-READ', 'U-BOB', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-ADMINS', 'U-CLAIRE', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-ENG-READ', 'U-ALICE', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-ENG-READ', 'U-CLAIRE', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-ENG-WRITE', 'U-CLAIRE', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-LEGAL-READ', 'U-BOB', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-SHARED-READ', 'U-BOB', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-SHARED-READ', 'U-CLAIRE', 'user'),
  (@snapshot_active_id, @demo_ad_source_id, 'G-B2S-SHARED-WRITE', 'U-ALICE', 'user');

INSERT INTO directory_effective_memberships (
  identity_source_id,
  snapshot_id,
  directory_user_id,
  directory_group_id,
  depth,
  path_hash,
  resolution_type
)
VALUES
  (@demo_ad_source_id, @snapshot_active_id, @du_alice_id, @dg_fin_read_id, 0, SHA2('alice-fin-read', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_alice_id, @dg_fin_write_id, 0, SHA2('alice-fin-write', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_claire_id, @dg_fin_read_id, 0, SHA2('claire-fin-read', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_bob_id, @dg_hr_read_id, 0, SHA2('bob-hr-read', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_claire_id, @dg_admins_id, 0, SHA2('claire-admins', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_alice_id, @dg_eng_read_id, 0, SHA2('alice-eng-read', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_claire_id, @dg_eng_read_id, 0, SHA2('claire-eng-read', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_claire_id, @dg_eng_write_id, 0, SHA2('claire-eng-write', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_bob_id, @dg_legal_read_id, 0, SHA2('bob-legal-read', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_bob_id, @dg_shared_read_id, 0, SHA2('bob-shared-read', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_claire_id, @dg_shared_read_id, 0, SHA2('claire-shared-read', 256), 'direct'),
  (@demo_ad_source_id, @snapshot_active_id, @du_alice_id, @dg_shared_write_id, 0, SHA2('alice-shared-write', 256), 'direct');

INSERT INTO directory_ous (identity_source_id, external_id, dn, name)
VALUES
  (@demo_openldap_source_id, 'OU-PEOPLE', 'ou=people,dc=ldap,dc=demo', 'People'),
  (@demo_openldap_source_id, 'OU-GROUPS', 'ou=groups,dc=ldap,dc=demo', 'Groups');

SET @ou_openldap_people_id := (SELECT id FROM directory_ous WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'OU-PEOPLE' LIMIT 1);
SET @ou_openldap_groups_id := (SELECT id FROM directory_ous WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'OU-GROUPS' LIMIT 1);

INSERT INTO directory_users (
  identity_source_id,
  external_id,
  object_guid,
  object_sid,
  upn,
  dn,
  when_changed,
  usn_changed,
  username,
  display_name,
  email,
  snapshot_version,
  snapshot_source,
  snapshot_hash,
  last_snapshot_at,
  ou_id
)
VALUES
  (@demo_local_source_id, 'L-ADMIN', NULL, NULL, 'demo.admin@local.demo', 'uid=demo.admin,ou=people,dc=local,dc=demo', UTC_TIMESTAMP() - INTERVAL 2 HOUR, 1001, 'demo.admin', 'Demo Admin', 'admin@local.demo', 1, 'local', SHA2('L-ADMIN', 256), UTC_TIMESTAMP() - INTERVAL 2 HOUR, NULL),
  (@demo_local_source_id, 'L-SUPPORT', NULL, NULL, 'demo.support@local.demo', 'uid=demo.support,ou=people,dc=local,dc=demo', UTC_TIMESTAMP() - INTERVAL 2 HOUR, 1002, 'demo.support', 'Demo Support', 'support@local.demo', 1, 'local', SHA2('L-SUPPORT', 256), UTC_TIMESTAMP() - INTERVAL 2 HOUR, NULL),
  (@demo_openldap_source_id, 'U-JDUPONT', NULL, NULL, 'jdupont@ldap.demo', 'uid=jdupont,ou=people,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 1201, 'jdupont', 'Jean Dupont', 'jdupont@ldap.demo', 1, 'openldap', SHA2('U-JDUPONT', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, @ou_openldap_people_id),
  (@demo_openldap_source_id, 'U-MMARTIN', NULL, NULL, 'mmartin@ldap.demo', 'uid=mmartin,ou=people,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 29 MINUTE, 1202, 'mmartin', 'Marie Martin', 'mmartin@ldap.demo', 1, 'openldap', SHA2('U-MMARTIN', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, @ou_openldap_people_id),
  (@demo_openldap_source_id, 'U-PBERNARD', NULL, NULL, 'pbernard@ldap.demo', 'uid=pbernard,ou=people,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 28 MINUTE, 1203, 'pbernard', 'Paul Bernard', 'pbernard@ldap.demo', 1, 'openldap', SHA2('U-PBERNARD', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, @ou_openldap_people_id),
  (@demo_openldap_source_id, 'U-CLEFEVRE', NULL, NULL, 'clefevre@ldap.demo', 'uid=clefevre,ou=people,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 27 MINUTE, 1204, 'clefevre', 'Claire Lefevre', 'clefevre@ldap.demo', 1, 'openldap', SHA2('U-CLEFEVRE', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, @ou_openldap_people_id),
  (@demo_openldap_source_id, 'U-AROBERT', NULL, NULL, 'arobert@ldap.demo', 'uid=arobert,ou=people,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 26 MINUTE, 1205, 'arobert', 'Alex Robert', 'arobert@ldap.demo', 1, 'openldap', SHA2('U-AROBERT', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE, @ou_openldap_people_id);

SET @du_local_admin_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_local_source_id AND external_id = 'L-ADMIN' LIMIT 1);
SET @du_local_support_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_local_source_id AND external_id = 'L-SUPPORT' LIMIT 1);
SET @du_jdupont_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'U-JDUPONT' LIMIT 1);
SET @du_mmartin_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'U-MMARTIN' LIMIT 1);
SET @du_pbernard_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'U-PBERNARD' LIMIT 1);
SET @du_clefevre_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'U-CLEFEVRE' LIMIT 1);
SET @du_arobert_id := (SELECT id FROM directory_users WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'U-AROBERT' LIMIT 1);

INSERT INTO identity_bindings (identity_id, directory_user_id)
VALUES
  (@identity_admin_id, @du_local_admin_id),
  (@identity_support_id, @du_local_support_id),
  (@identity_jdupont_id, @du_jdupont_id),
  (@identity_mmartin_id, @du_mmartin_id),
  (@identity_pbernard_id, @du_pbernard_id),
  (@identity_clefevre_id, @du_clefevre_id),
  (@identity_arobert_id, @du_arobert_id);

INSERT INTO directory_groups (
  identity_source_id,
  external_id,
  dn,
  when_changed,
  usn_changed,
  name,
  code,
  description,
  snapshot_version,
  snapshot_source,
  snapshot_hash,
  last_snapshot_at
)
VALUES
  (@demo_local_source_id, 'LOCAL-ADMIN', 'cn=LOCAL_ADMIN,ou=groups,dc=local,dc=demo', UTC_TIMESTAMP() - INTERVAL 2 HOUR, 2001, 'LOCAL_ADMIN', 'LOCAL_ADMIN', 'Local administrators', 1, 'local', SHA2('LOCAL-ADMIN', 256), UTC_TIMESTAMP() - INTERVAL 2 HOUR),
  (@demo_local_source_id, 'LOCAL-SUPPORT', 'cn=LOCAL_SUPPORT,ou=groups,dc=local,dc=demo', UTC_TIMESTAMP() - INTERVAL 2 HOUR, 2002, 'LOCAL_SUPPORT', 'LOCAL_SUPPORT', 'Local support operators', 1, 'local', SHA2('LOCAL-SUPPORT', 256), UTC_TIMESTAMP() - INTERVAL 2 HOUR),
  (@demo_openldap_source_id, 'FINANCE_RW', 'cn=FINANCE_RW,ou=groups,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 3001, 'FINANCE_RW', 'FINANCE_RW', 'Finance read/write access', 1, 'openldap', SHA2('FINANCE_RW', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE),
  (@demo_openldap_source_id, 'FINANCE_RO', 'cn=FINANCE_RO,ou=groups,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 3002, 'FINANCE_RO', 'FINANCE_RO', 'Finance read-only access', 1, 'openldap', SHA2('FINANCE_RO', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE),
  (@demo_openldap_source_id, 'RH_RW', 'cn=RH_RW,ou=groups,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 3003, 'RH_RW', 'RH_RW', 'Human resources read/write access', 1, 'openldap', SHA2('RH_RW', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE),
  (@demo_openldap_source_id, 'RH_RO', 'cn=RH_RO,ou=groups,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 3004, 'RH_RO', 'RH_RO', 'Human resources read-only access', 1, 'openldap', SHA2('RH_RO', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE),
  (@demo_openldap_source_id, 'IT_ADMIN', 'cn=IT_ADMIN,ou=groups,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 3005, 'IT_ADMIN', 'IT_ADMIN', 'IT administrative access', 1, 'openldap', SHA2('IT_ADMIN', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE),
  (@demo_openldap_source_id, 'SALES_RW', 'cn=SALES_RW,ou=groups,dc=ldap,dc=demo', UTC_TIMESTAMP() - INTERVAL 30 MINUTE, 3006, 'SALES_RW', 'SALES_RW', 'Sales read/write access', 1, 'openldap', SHA2('SALES_RW', 256), UTC_TIMESTAMP() - INTERVAL 30 MINUTE);

SET @dg_local_admin_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_local_source_id AND external_id = 'LOCAL-ADMIN' LIMIT 1);
SET @dg_local_support_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_local_source_id AND external_id = 'LOCAL-SUPPORT' LIMIT 1);
SET @dg_finance_rw_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'FINANCE_RW' LIMIT 1);
SET @dg_finance_ro_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'FINANCE_RO' LIMIT 1);
SET @dg_rh_rw_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'RH_RW' LIMIT 1);
SET @dg_rh_ro_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'RH_RO' LIMIT 1);
SET @dg_it_admin_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'IT_ADMIN' LIMIT 1);
SET @dg_sales_rw_id := (SELECT id FROM directory_groups WHERE identity_source_id = @demo_openldap_source_id AND external_id = 'SALES_RW' LIMIT 1);

INSERT INTO directory_group_members (group_id, directory_user_id)
VALUES
  (@dg_local_admin_id, @du_local_admin_id),
  (@dg_local_support_id, @du_local_support_id),
  (@dg_local_support_id, @du_local_admin_id),
  (@dg_finance_rw_id, @du_jdupont_id),
  (@dg_finance_rw_id, @du_mmartin_id),
  (@dg_finance_ro_id, @du_jdupont_id),
  (@dg_finance_ro_id, @du_mmartin_id),
  (@dg_finance_ro_id, @du_arobert_id),
  (@dg_rh_rw_id, @du_pbernard_id),
  (@dg_rh_ro_id, @du_pbernard_id),
  (@dg_rh_ro_id, @du_mmartin_id),
  (@dg_it_admin_id, @du_clefevre_id),
  (@dg_it_admin_id, @du_jdupont_id),
  (@dg_sales_rw_id, @du_arobert_id),
  (@dg_sales_rw_id, @du_clefevre_id);

INSERT INTO directory_snapshots (
  identity_source_id,
  version,
  status,
  snapshot_source,
  initiated_by,
  correlation_id,
  started_at,
  completed_at,
  finished_at,
  activated_at,
  summary_json
)
VALUES
  (
    @demo_local_source_id,
    1,
    'ACTIVE',
    'local',
    'demo-seed',
    'demo-local-snapshot-active',
    UTC_TIMESTAMP(6) - INTERVAL 2 HOUR,
    UTC_TIMESTAMP(6) - INTERVAL 2 HOUR,
    UTC_TIMESTAMP(6) - INTERVAL 2 HOUR,
    UTC_TIMESTAMP(6) - INTERVAL 90 MINUTE,
    JSON_OBJECT(
      'users', 2,
      'groups', 2,
      'memberships', 3,
      'managers', JSON_ARRAY(
        JSON_OBJECT('group', 'LOCAL_ADMIN', 'manager', 'Demo Admin'),
        JSON_OBJECT('group', 'LOCAL_SUPPORT', 'manager', 'Demo Support')
      ),
      'attributes', JSON_OBJECT('source', 'local', 'object_class', 'person')
    )
  ),
  (
    @demo_openldap_source_id,
    1,
    'ACTIVE',
    'openldap',
    'demo-seed',
    'demo-openldap-snapshot-active',
    UTC_TIMESTAMP(6) - INTERVAL 30 MINUTE,
    UTC_TIMESTAMP(6) - INTERVAL 28 MINUTE,
    UTC_TIMESTAMP(6) - INTERVAL 28 MINUTE,
    UTC_TIMESTAMP(6) - INTERVAL 27 MINUTE,
    JSON_OBJECT(
      'users', 5,
      'groups', 6,
      'memberships', 15,
      'managers', JSON_ARRAY(
        JSON_OBJECT('group', 'FINANCE_RW', 'manager', 'jdupont'),
        JSON_OBJECT('group', 'FINANCE_RO', 'manager', 'mmartin'),
        JSON_OBJECT('group', 'RH_RW', 'manager', 'pbernard'),
        JSON_OBJECT('group', 'RH_RO', 'manager', 'pbernard'),
        JSON_OBJECT('group', 'IT_ADMIN', 'manager', 'clefevre'),
        JSON_OBJECT('group', 'SALES_RW', 'manager', 'arobert')
      ),
      'attributes', JSON_OBJECT(
        'source', 'openldap',
        'user_object_class', 'inetOrgPerson',
        'group_object_class', 'groupOfNames',
        'member_attribute', 'member',
        'manager_attribute', 'manager'
      )
    )
  );

SET @snapshot_local_id := (SELECT id FROM directory_snapshots WHERE identity_source_id = @demo_local_source_id AND version = 1 LIMIT 1);
SET @snapshot_openldap_id := (SELECT id FROM directory_snapshots WHERE identity_source_id = @demo_openldap_source_id AND version = 1 LIMIT 1);

INSERT INTO directory_snapshot_users (
  snapshot_id,
  identity_source_id,
  external_id,
  object_guid,
  object_sid,
  upn,
  dn,
  when_changed,
  usn_changed,
  username,
  display_name,
  email,
  source,
  snapshot_version,
  is_active
)
SELECT
  @snapshot_local_id,
  identity_source_id,
  external_id,
  object_guid,
  object_sid,
  upn,
  dn,
  when_changed,
  usn_changed,
  username,
  display_name,
  email,
  'seed',
  snapshot_version,
  1
FROM directory_users
WHERE identity_source_id = @demo_local_source_id;

INSERT INTO directory_snapshot_groups (
  snapshot_id,
  identity_source_id,
  external_id,
  dn,
  when_changed,
  usn_changed,
  name,
  code,
  description,
  snapshot_version,
  is_active
)
SELECT
  @snapshot_local_id,
  identity_source_id,
  external_id,
  dn,
  when_changed,
  usn_changed,
  name,
  code,
  description,
  snapshot_version,
  1
FROM directory_groups
WHERE identity_source_id = @demo_local_source_id;

INSERT INTO directory_snapshot_users (
  snapshot_id,
  identity_source_id,
  external_id,
  object_guid,
  object_sid,
  upn,
  dn,
  when_changed,
  usn_changed,
  username,
  display_name,
  email,
  source,
  snapshot_version,
  is_active
)
SELECT
  @snapshot_openldap_id,
  identity_source_id,
  external_id,
  object_guid,
  object_sid,
  upn,
  dn,
  when_changed,
  usn_changed,
  username,
  display_name,
  email,
  'seed',
  snapshot_version,
  1
FROM directory_users
WHERE identity_source_id = @demo_openldap_source_id;

INSERT INTO directory_snapshot_groups (
  snapshot_id,
  identity_source_id,
  external_id,
  dn,
  when_changed,
  usn_changed,
  name,
  code,
  description,
  snapshot_version,
  is_active
)
SELECT
  @snapshot_openldap_id,
  identity_source_id,
  external_id,
  dn,
  when_changed,
  usn_changed,
  name,
  code,
  description,
  snapshot_version,
  1
FROM directory_groups
WHERE identity_source_id = @demo_openldap_source_id;

INSERT INTO directory_snapshot_memberships (
  snapshot_id,
  identity_source_id,
  group_external_id,
  member_external_id,
  member_type
)
VALUES
  (@snapshot_local_id, @demo_local_source_id, 'LOCAL-ADMIN', 'L-ADMIN', 'user'),
  (@snapshot_local_id, @demo_local_source_id, 'LOCAL-SUPPORT', 'L-ADMIN', 'user'),
  (@snapshot_local_id, @demo_local_source_id, 'LOCAL-SUPPORT', 'L-SUPPORT', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'FINANCE_RW', 'U-JDUPONT', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'FINANCE_RW', 'U-MMARTIN', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'FINANCE_RO', 'U-JDUPONT', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'FINANCE_RO', 'U-MMARTIN', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'FINANCE_RO', 'U-AROBERT', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'RH_RW', 'U-PBERNARD', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'RH_RO', 'U-PBERNARD', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'RH_RO', 'U-MMARTIN', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'IT_ADMIN', 'U-CLEFEVRE', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'IT_ADMIN', 'U-JDUPONT', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'SALES_RW', 'U-AROBERT', 'user'),
  (@snapshot_openldap_id, @demo_openldap_source_id, 'SALES_RW', 'U-CLEFEVRE', 'user');

-- ------------------------------------------------------------
-- Storage topology, policies, owners, profiles and governance.
-- ------------------------------------------------------------

INSERT INTO zones (name, code, description)
VALUES
  ('Demo Paris', 'DEMO-PARIS', 'Primary demo zone for SMB storage'),
  ('Demo Lyon', 'DEMO-LYON', 'Secondary demo zone with a warning state'),
  ('Demo Marseille', 'DEMO-MARSEILLE', 'Engineering-oriented NFS zone'),
  ('Demo Nantes', 'DEMO-NANTES', 'Legal and records management zone');

SET @zone_paris_id := (SELECT id FROM zones WHERE code = 'DEMO-PARIS' ORDER BY id DESC LIMIT 1);
SET @zone_lyon_id := (SELECT id FROM zones WHERE code = 'DEMO-LYON' ORDER BY id DESC LIMIT 1);
SET @zone_marseille_id := (SELECT id FROM zones WHERE code = 'DEMO-MARSEILLE' ORDER BY id DESC LIMIT 1);
SET @zone_nantes_id := (SELECT id FROM zones WHERE code = 'DEMO-NANTES' ORDER BY id DESC LIMIT 1);

INSERT INTO tags (name, color)
VALUES
  ('Demo Critical', '#dc2626'),
  ('Demo PII', '#9333ea'),
  ('Demo Finance', '#2563eb'),
  ('Demo HR', '#16a34a'),
  ('Demo Engineering', '#0f766e'),
  ('Demo Legal', '#b45309'),
  ('Demo Shared', '#1d4ed8'),
  ('Demo Sandbox', '#6b7280');

SET @tag_critical_id := (SELECT id FROM tags WHERE name = 'Demo Critical' ORDER BY id DESC LIMIT 1);
SET @tag_pii_id := (SELECT id FROM tags WHERE name = 'Demo PII' ORDER BY id DESC LIMIT 1);
SET @tag_finance_id := (SELECT id FROM tags WHERE name = 'Demo Finance' ORDER BY id DESC LIMIT 1);
SET @tag_hr_id := (SELECT id FROM tags WHERE name = 'Demo HR' ORDER BY id DESC LIMIT 1);
SET @tag_engineering_id := (SELECT id FROM tags WHERE name = 'Demo Engineering' ORDER BY id DESC LIMIT 1);
SET @tag_legal_id := (SELECT id FROM tags WHERE name = 'Demo Legal' ORDER BY id DESC LIMIT 1);
SET @tag_shared_id := (SELECT id FROM tags WHERE name = 'Demo Shared' ORDER BY id DESC LIMIT 1);
SET @tag_sandbox_id := (SELECT id FROM tags WHERE name = 'Demo Sandbox' ORDER BY id DESC LIMIT 1);

INSERT INTO storage_endpoints (
  zone_id,
  identity_source_id,
  name,
  endpoint_type,
  protocol,
  host,
  port,
  base_path,
  auth_type,
  bind_dn,
  bind_password_ref,
  capabilities,
  description,
  external_id,
  sub_ou_dn,
  naming_template,
  last_probe_status,
  last_probe_at,
  last_probe_message,
  is_active,
  status
)
VALUES
  (@zone_paris_id, @demo_ad_source_id, 'Demo SMB Paris', 'windows_file_server', 'smb', 'fs01.corp.demo', 445, '\\\\fs01\\corp', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs01-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Demo Windows file server', 'DEMO-ENDPOINT-SMB-PARIS', 'OU=BornToShare,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'success', UTC_TIMESTAMP() - INTERVAL 5 MINUTE, 'SMB probe succeeded', 1, 'active'),
  (@zone_lyon_id, @demo_ad_source_id, 'Demo SMB Lyon', 'windows_file_server', 'smb', 'fs02.corp.demo', 445, '\\\\fs02\\corp', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs02-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Demo endpoint with degraded probe', 'DEMO-ENDPOINT-SMB-LYON', 'OU=BornToShare-Lyon,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'failed', UTC_TIMESTAMP() - INTERVAL 35 MINUTE, 'Last probe returned a latency warning', 1, 'warning'),
  (@zone_marseille_id, @demo_ad_source_id, 'Demo NFS Marseille', 'linux_file_server', 'nfs', 'nfs01.corp.demo', 2049, '/srv/shares', 'kerberos', NULL, NULL, JSON_OBJECT('acl_apply', false, 'probe', true, 'inventory', true), 'Demo Linux engineering server', 'DEMO-ENDPOINT-NFS-MARSEILLE', 'OU=BornToShare-Marseille,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'success', UTC_TIMESTAMP() - INTERVAL 8 MINUTE, 'NFS probe succeeded', 1, 'active'),
  (@zone_nantes_id, @demo_ad_source_id, 'Demo SMB Nantes', 'windows_file_server', 'smb', 'fs03.corp.demo', 445, '\\\\fs03\\records', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs03-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Demo legal records server', 'DEMO-ENDPOINT-SMB-NANTES', 'OU=BornToShare-Nantes,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'running', UTC_TIMESTAMP() - INTERVAL 2 MINUTE, 'Probe currently running', 1, 'active'),
  (@zone_paris_id, @demo_ad_source_id, 'Demo SMB Paris Lab', 'windows_file_server', 'smb', 'labfs01.corp.demo', 445, '\\\\labfs01\\sandbox', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/lab-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Demo isolated lab server', 'DEMO-ENDPOINT-SMB-PARIS-LAB', 'OU=BornToShare-Lab,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'unknown', UTC_TIMESTAMP() - INTERVAL 3 HOUR, 'No recent probe result', 1, 'maintenance');

SET @endpoint_paris_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-PARIS' ORDER BY id DESC LIMIT 1);
SET @endpoint_lyon_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-LYON' ORDER BY id DESC LIMIT 1);
SET @endpoint_marseille_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-NFS-MARSEILLE' ORDER BY id DESC LIMIT 1);
SET @endpoint_nantes_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-NANTES' ORDER BY id DESC LIMIT 1);
SET @endpoint_paris_lab_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-PARIS-LAB' ORDER BY id DESC LIMIT 1);

INSERT INTO zone_provisioning_policy (zone_id, enabled, policy_mode, ou_strategy, static_ou_dn, base_ou_dn)
VALUES
  (@zone_paris_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'ZONE_STATIC', 'OU=BornToShare,OU=Groups,DC=corp,DC=demo', 'OU=Groups,DC=corp,DC=demo'),
  (@zone_lyon_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'IDENTITY_DEFAULT', NULL, 'OU=Groups,DC=corp,DC=demo'),
  (@zone_marseille_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'ZONE_STATIC', 'OU=BornToShare-Marseille,OU=Groups,DC=corp,DC=demo', 'OU=Groups,DC=corp,DC=demo'),
  (@zone_nantes_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'ZONE_STATIC', 'OU=BornToShare-Nantes,OU=Groups,DC=corp,DC=demo', 'OU=Groups,DC=corp,DC=demo')
ON DUPLICATE KEY UPDATE
  enabled = VALUES(enabled),
  policy_mode = VALUES(policy_mode),
  ou_strategy = VALUES(ou_strategy),
  static_ou_dn = VALUES(static_ou_dn),
  base_ou_dn = VALUES(base_ou_dn);

INSERT INTO storage_roots (
  storage_endpoint_id,
  parent_storage_root_id,
  name,
  root_path,
  normalized_root_path,
  inherit_owners,
  inherit_tags,
  status,
  last_probe_status,
  last_probe_at,
  last_probe_message,
  last_discovery_at,
  discovered_permissions_json,
  discovered_tree_json,
  needs_revalidation,
  revalidation_reason
)
VALUES
  (@endpoint_paris_id, NULL, 'Finance', '\\\\fs01\\corp\\finance', '/corp/finance', 0, 0, 'active', 'success', UTC_TIMESTAMP() - INTERVAL 4 MINUTE, 'ACL inventory matched expected groups', UTC_TIMESTAMP() - INTERVAL 4 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(JSON_OBJECT('group', 'B2S_FINANCE_READ', 'permission', 'READ'), JSON_OBJECT('group', 'B2S_FINANCE_WRITE', 'permission', 'WRITE')), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 4 MINUTE), JSON_OBJECT('children', JSON_ARRAY('AP', 'AR')), 0, NULL),
  (@endpoint_lyon_id, NULL, 'HR', '\\\\fs02\\corp\\hr', '/corp/hr', 0, 0, 'warning', 'failed', UTC_TIMESTAMP() - INTERVAL 35 MINUTE, 'Probe latency over threshold', UTC_TIMESTAMP() - INTERVAL 40 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(JSON_OBJECT('group', 'B2S_HR_READ', 'permission', 'READ')), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 40 MINUTE), JSON_OBJECT('children', JSON_ARRAY('Onboarding')), 1, 'Probe warning requires review'),
  (@endpoint_marseille_id, NULL, 'Engineering', '/srv/shares/engineering', '/corp/engineering', 0, 0, 'active', 'success', UTC_TIMESTAMP() - INTERVAL 8 MINUTE, 'Engineering share inventory succeeded', UTC_TIMESTAMP() - INTERVAL 8 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(JSON_OBJECT('group', 'B2S_ENG_READ', 'permission', 'READ'), JSON_OBJECT('group', 'B2S_ENG_WRITE', 'permission', 'WRITE')), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 8 MINUTE), JSON_OBJECT('children', JSON_ARRAY('Builds')), 0, NULL),
  (@endpoint_marseille_id, NULL, 'Shared Projects', '/srv/shares/projects/shared', '/corp/projects/shared', 0, 0, 'active', 'success', UTC_TIMESTAMP() - INTERVAL 7 MINUTE, 'Shared projects probe succeeded', UTC_TIMESTAMP() - INTERVAL 7 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(JSON_OBJECT('group', 'B2S_SHARED_READ', 'permission', 'READ'), JSON_OBJECT('group', 'B2S_SHARED_WRITE', 'permission', 'WRITE')), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 7 MINUTE), JSON_OBJECT('children', JSON_ARRAY()), 0, NULL),
  (@endpoint_nantes_id, NULL, 'Legal', '\\\\fs03\\records\\legal', '/corp/legal', 0, 0, 'active', 'running', UTC_TIMESTAMP() - INTERVAL 2 MINUTE, 'Probe running for legal endpoint', UTC_TIMESTAMP() - INTERVAL 20 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(JSON_OBJECT('group', 'B2S_LEGAL_READ', 'permission', 'READ')), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 20 MINUTE), JSON_OBJECT('children', JSON_ARRAY('Contracts')), 0, NULL),
  (@endpoint_paris_lab_id, NULL, 'Lab Sandbox', '\\\\labfs01\\sandbox', '/corp/labs/sandbox', 0, 0, 'maintenance', 'unknown', UTC_TIMESTAMP() - INTERVAL 3 HOUR, 'Lab endpoint has no fresh probe', UTC_TIMESTAMP() - INTERVAL 1 DAY, JSON_OBJECT('permissions', JSON_ARRAY(), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 1 DAY), JSON_OBJECT('children', JSON_ARRAY()), 1, 'Awaiting fresh probe');

SET @root_finance_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_paris_id AND normalized_root_path = '/corp/finance' LIMIT 1);
SET @root_hr_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_lyon_id AND normalized_root_path = '/corp/hr' LIMIT 1);
SET @root_engineering_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_marseille_id AND normalized_root_path = '/corp/engineering' LIMIT 1);
SET @root_shared_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_marseille_id AND normalized_root_path = '/corp/projects/shared' LIMIT 1);
SET @root_legal_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_nantes_id AND normalized_root_path = '/corp/legal' LIMIT 1);
SET @root_lab_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_paris_lab_id AND normalized_root_path = '/corp/labs/sandbox' LIMIT 1);

INSERT INTO storage_roots (
  storage_endpoint_id,
  parent_storage_root_id,
  name,
  root_path,
  normalized_root_path,
  inherit_owners,
  inherit_tags,
  status,
  last_probe_status,
  last_probe_at,
  last_probe_message,
  last_discovery_at,
  discovered_permissions_json,
  discovered_tree_json,
  needs_revalidation,
  revalidation_reason
)
VALUES
  (@endpoint_paris_id, @root_finance_id, 'Finance AP', '\\\\fs01\\corp\\finance\\ap', '/corp/finance/ap', 1, 1, 'active', 'success', UTC_TIMESTAMP() - INTERVAL 4 MINUTE, 'Inherited controls verified', UTC_TIMESTAMP() - INTERVAL 4 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 4 MINUTE), JSON_OBJECT('children', JSON_ARRAY()), 0, NULL),
  (@endpoint_paris_id, @root_finance_id, 'Finance AR', '\\\\fs01\\corp\\finance\\ar', '/corp/finance/ar', 1, 1, 'active', 'success', UTC_TIMESTAMP() - INTERVAL 4 MINUTE, 'Inherited controls verified', UTC_TIMESTAMP() - INTERVAL 4 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 4 MINUTE), JSON_OBJECT('children', JSON_ARRAY()), 0, NULL),
  (@endpoint_lyon_id, @root_hr_id, 'HR Onboarding', '\\\\fs02\\corp\\hr\\onboarding', '/corp/hr/onboarding', 1, 1, 'warning', 'failed', UTC_TIMESTAMP() - INTERVAL 35 MINUTE, 'Inherited controls need review', UTC_TIMESTAMP() - INTERVAL 40 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 40 MINUTE), JSON_OBJECT('children', JSON_ARRAY()), 1, 'Parent endpoint probe warning'),
  (@endpoint_marseille_id, @root_engineering_id, 'Engineering Builds', '/srv/shares/engineering/builds', '/corp/engineering/builds', 1, 1, 'active', 'success', UTC_TIMESTAMP() - INTERVAL 8 MINUTE, 'Builds subtree verified', UTC_TIMESTAMP() - INTERVAL 8 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 8 MINUTE), JSON_OBJECT('children', JSON_ARRAY()), 0, NULL),
  (@endpoint_nantes_id, @root_legal_id, 'Legal Contracts', '\\\\fs03\\records\\legal\\contracts', '/corp/legal/contracts', 1, 1, 'active', 'running', UTC_TIMESTAMP() - INTERVAL 2 MINUTE, 'Contracts subtree scan in progress', UTC_TIMESTAMP() - INTERVAL 20 MINUTE, JSON_OBJECT('permissions', JSON_ARRAY(), 'discovered_at', UTC_TIMESTAMP() - INTERVAL 20 MINUTE), JSON_OBJECT('children', JSON_ARRAY()), 0, NULL);

SET @root_fin_ap_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_paris_id AND normalized_root_path = '/corp/finance/ap' LIMIT 1);
SET @root_fin_ar_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_paris_id AND normalized_root_path = '/corp/finance/ar' LIMIT 1);
SET @root_hr_onboarding_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_lyon_id AND normalized_root_path = '/corp/hr/onboarding' LIMIT 1);
SET @root_eng_builds_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_marseille_id AND normalized_root_path = '/corp/engineering/builds' LIMIT 1);
SET @root_legal_contracts_id := (SELECT id FROM storage_roots WHERE storage_endpoint_id = @endpoint_nantes_id AND normalized_root_path = '/corp/legal/contracts' LIMIT 1);

INSERT IGNORE INTO storage_root_tags (storage_root_id, tag_id)
VALUES
  (@root_finance_id, @tag_critical_id),
  (@root_finance_id, @tag_pii_id),
  (@root_finance_id, @tag_finance_id),
  (@root_hr_id, @tag_hr_id),
  (@root_hr_onboarding_id, @tag_pii_id),
  (@root_engineering_id, @tag_engineering_id),
  (@root_eng_builds_id, @tag_engineering_id),
  (@root_shared_id, @tag_shared_id),
  (@root_legal_id, @tag_legal_id),
  (@root_legal_contracts_id, @tag_legal_id),
  (@root_lab_id, @tag_sandbox_id);

INSERT IGNORE INTO storage_root_roles (root_id, identity_id, role, assigned_by)
VALUES
  (@root_finance_id, @identity_claire_id, 'guardian', @identity_admin_id),
  (@root_hr_id, @identity_bob_id, 'guardian', @identity_admin_id),
  (@root_engineering_id, @identity_claire_id, 'guardian', @identity_admin_id),
  (@root_legal_id, @identity_alice_id, 'guardian', @identity_admin_id),
  (@root_shared_id, @identity_bob_id, 'guardian', @identity_admin_id),
  (@root_fin_ap_id, @identity_claire_id, 'guardian', @identity_admin_id),
  (@root_fin_ar_id, @identity_alice_id, 'guardian', @identity_admin_id),
  (@root_hr_onboarding_id, @identity_bob_id, 'guardian', @identity_admin_id),
  (@root_eng_builds_id, @identity_claire_id, 'guardian', @identity_admin_id),
  (@root_legal_contracts_id, @identity_alice_id, 'guardian', @identity_admin_id),
  (@root_lab_id, @identity_jdupont_id, 'guardian', @identity_admin_id);

INSERT INTO naming_policy_overrides (
  scope_type,
  scope_id,
  override_enabled,
  group_prefix,
  template,
  normalize_uppercase,
  max_sam_length,
  replace_map_json,
  rootcode_strategy
)
VALUES
  ('zone', @zone_paris_id, 1, 'B2S', '{PREFIX}_{ROOTCODE}_{PERM}', 1, 64, JSON_OBJECT(' ', '_'), 'BASENAME'),
  ('storage_endpoint', @endpoint_lyon_id, 1, 'B2S-LYO', '{PREFIX}_{ROOTCODE}_{PERM}', 1, 64, JSON_OBJECT(' ', '_', '/', '_'), 'BASENAME'),
  ('storage_root', @root_finance_id, 1, 'FIN', '{PREFIX}_{ROOTCODE}_{PERM}', 1, 64, JSON_OBJECT(' ', '_'), 'BASENAME'),
  ('zone', @zone_marseille_id, 1, 'ENG', '{PREFIX}_{ROOTCODE}_{PERM}', 1, 64, JSON_OBJECT(' ', '_', '.', '_'), 'BASENAME'),
  ('storage_endpoint', @endpoint_nantes_id, 1, 'LEG', '{PREFIX}_{ROOTCODE}_{PERM}', 1, 64, JSON_OBJECT(' ', '_'), 'BASENAME'),
  ('storage_root', @root_shared_id, 1, 'SHR', '{PREFIX}_{ROOTCODE}_{PERM}', 1, 64, JSON_OBJECT(' ', '_'), 'BASENAME')
ON DUPLICATE KEY UPDATE
  override_enabled = VALUES(override_enabled),
  group_prefix = VALUES(group_prefix),
  template = VALUES(template),
  normalize_uppercase = VALUES(normalize_uppercase),
  max_sam_length = VALUES(max_sam_length),
  replace_map_json = VALUES(replace_map_json),
  rootcode_strategy = VALUES(rootcode_strategy);

INSERT IGNORE INTO storage_root_access_profiles (
  storage_root_id,
  access_level_code,
  group_name,
  group_external_id,
  status,
  error_message
)
VALUES
  (@root_finance_id, 'READ', 'B2S_FINANCE_READ', 'G-B2S-FINANCE-READ', 'SUCCEEDED', NULL),
  (@root_finance_id, 'WRITE', 'B2S_FINANCE_WRITE', 'G-B2S-FINANCE-WRITE', 'SUCCEEDED', NULL),
  (@root_hr_id, 'READ', 'B2S_HR_READ', 'G-B2S-HR-READ', 'SUCCEEDED', NULL),
  (@root_hr_id, 'WRITE', 'B2S_HR_WRITE', NULL, 'FAILED', 'Demo failure: write group could not be created'),
  (@root_engineering_id, 'READ', 'B2S_ENG_READ', 'G-B2S-ENG-READ', 'SUCCEEDED', NULL),
  (@root_engineering_id, 'WRITE', 'B2S_ENG_WRITE', 'G-B2S-ENG-WRITE', 'SUCCEEDED', NULL),
  (@root_shared_id, 'READ', 'B2S_SHARED_READ', 'G-B2S-SHARED-READ', 'SUCCEEDED', NULL),
  (@root_shared_id, 'WRITE', 'B2S_SHARED_WRITE', 'G-B2S-SHARED-WRITE', 'SUCCEEDED', NULL),
  (@root_legal_id, 'READ', 'B2S_LEGAL_READ', 'G-B2S-LEGAL-READ', 'SUCCEEDED', NULL),
  (@root_lab_id, 'READ', 'B2S_LAB_READ', NULL, 'PENDING', NULL);

SET @srap_fin_read_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_finance_id AND access_level_code = 'READ' LIMIT 1);
SET @srap_fin_write_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_finance_id AND access_level_code = 'WRITE' LIMIT 1);
SET @srap_hr_read_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_hr_id AND access_level_code = 'READ' LIMIT 1);
SET @srap_hr_write_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_hr_id AND access_level_code = 'WRITE' LIMIT 1);
SET @srap_eng_read_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_engineering_id AND access_level_code = 'READ' LIMIT 1);
SET @srap_eng_write_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_engineering_id AND access_level_code = 'WRITE' LIMIT 1);
SET @srap_shared_read_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_shared_id AND access_level_code = 'READ' LIMIT 1);
SET @srap_shared_write_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_shared_id AND access_level_code = 'WRITE' LIMIT 1);
SET @srap_legal_read_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_legal_id AND access_level_code = 'READ' LIMIT 1);
SET @srap_lab_read_id := (SELECT id FROM storage_root_access_profiles WHERE storage_root_id = @root_lab_id AND access_level_code = 'READ' LIMIT 1);

-- ------------------------------------------------------------
-- Large demo expansion: extra zones, endpoints and policies.
-- ------------------------------------------------------------

INSERT INTO zones (name, code, description)
VALUES
  ('Demo Lille', 'DEMO-LILLE', 'Sales-oriented demo zone'),
  ('Demo Bordeaux', 'DEMO-BORDEAUX', 'Operations-oriented demo zone'),
  ('Demo Toulouse', 'DEMO-TOULOUSE', 'Shared services demo zone'),
  ('Demo Nice', 'DEMO-NICE', 'Compliance-oriented demo zone'),
  ('Demo Strasbourg', 'DEMO-STRASBOURG', 'Archive-oriented demo zone'),
  ('Demo Rennes', 'DEMO-RENNES', 'Sandbox-oriented demo zone');

SET @zone_lille_id := (SELECT id FROM zones WHERE code = 'DEMO-LILLE' ORDER BY id DESC LIMIT 1);
SET @zone_bordeaux_id := (SELECT id FROM zones WHERE code = 'DEMO-BORDEAUX' ORDER BY id DESC LIMIT 1);
SET @zone_toulouse_id := (SELECT id FROM zones WHERE code = 'DEMO-TOULOUSE' ORDER BY id DESC LIMIT 1);
SET @zone_nice_id := (SELECT id FROM zones WHERE code = 'DEMO-NICE' ORDER BY id DESC LIMIT 1);
SET @zone_strasbourg_id := (SELECT id FROM zones WHERE code = 'DEMO-STRASBOURG' ORDER BY id DESC LIMIT 1);
SET @zone_rennes_id := (SELECT id FROM zones WHERE code = 'DEMO-RENNES' ORDER BY id DESC LIMIT 1);

INSERT INTO zone_provisioning_policy (zone_id, enabled, policy_mode, ou_strategy, static_ou_dn, base_ou_dn)
VALUES
  (@zone_lille_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'ZONE_STATIC', 'OU=BornToShare-Lille,OU=Groups,DC=corp,DC=demo', 'OU=Groups,DC=corp,DC=demo'),
  (@zone_bordeaux_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'IDENTITY_DEFAULT', NULL, 'OU=Groups,DC=corp,DC=demo'),
  (@zone_toulouse_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'ZONE_STATIC', 'OU=BornToShare-Toulouse,OU=Groups,DC=corp,DC=demo', 'OU=Groups,DC=corp,DC=demo'),
  (@zone_nice_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'ZONE_STATIC', 'OU=BornToShare-Nice,OU=Groups,DC=corp,DC=demo', 'OU=Groups,DC=corp,DC=demo'),
  (@zone_strasbourg_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'ZONE_STATIC', 'OU=BornToShare-Strasbourg,OU=Groups,DC=corp,DC=demo', 'OU=Groups,DC=corp,DC=demo'),
  (@zone_rennes_id, 1, 'ON_FIRST_ACCESS_REQUEST', 'IDENTITY_DEFAULT', NULL, 'OU=Groups,DC=corp,DC=demo')
ON DUPLICATE KEY UPDATE
  enabled = VALUES(enabled),
  policy_mode = VALUES(policy_mode),
  ou_strategy = VALUES(ou_strategy),
  static_ou_dn = VALUES(static_ou_dn),
  base_ou_dn = VALUES(base_ou_dn);

INSERT INTO storage_endpoints (
  zone_id,
  identity_source_id,
  name,
  endpoint_type,
  protocol,
  host,
  port,
  base_path,
  auth_type,
  bind_dn,
  bind_password_ref,
  capabilities,
  description,
  external_id,
  sub_ou_dn,
  naming_template,
  last_probe_status,
  last_probe_at,
  last_probe_message,
  is_active,
  status
)
VALUES
  (@zone_lille_id, @demo_ad_source_id, 'Demo SMB Lille Sales', 'windows_file_server', 'smb', 'fs04.corp.demo', 445, '\\\\fs04\\sales', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs04-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Sales demo endpoint', 'DEMO-ENDPOINT-SMB-LILLE-SALES', 'OU=BornToShare-Lille,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'success', UTC_TIMESTAMP() - INTERVAL 11 MINUTE, 'SMB probe succeeded', 1, 'active'),
  (@zone_bordeaux_id, @demo_ad_source_id, 'Demo NFS Bordeaux Operations', 'linux_file_server', 'nfs', 'nfs02.corp.demo', 2049, '/srv/ops', 'kerberos', NULL, NULL, JSON_OBJECT('acl_apply', false, 'probe', true), 'Operations demo endpoint', 'DEMO-ENDPOINT-NFS-BORDEAUX-OPS', 'OU=BornToShare-Bordeaux,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'failed', UTC_TIMESTAMP() - INTERVAL 23 MINUTE, 'Operations endpoint probe latency warning', 1, 'warning'),
  (@zone_toulouse_id, @demo_ad_source_id, 'Demo SMB Toulouse Shared', 'windows_file_server', 'smb', 'fs05.corp.demo', 445, '\\\\fs05\\shared', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs05-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Shared services endpoint', 'DEMO-ENDPOINT-SMB-TOULOUSE-SHARED', 'OU=BornToShare-Toulouse,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'success', UTC_TIMESTAMP() - INTERVAL 7 MINUTE, 'SMB probe succeeded', 1, 'active'),
  (@zone_nice_id, @demo_ad_source_id, 'Demo SMB Nice Compliance', 'windows_file_server', 'smb', 'fs06.corp.demo', 445, '\\\\fs06\\compliance', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs06-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Compliance endpoint', 'DEMO-ENDPOINT-SMB-NICE-COMPLIANCE', 'OU=BornToShare-Nice,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'failed', UTC_TIMESTAMP() - INTERVAL 44 MINUTE, 'Compliance endpoint probe failed', 1, 'warning'),
  (@zone_strasbourg_id, @demo_ad_source_id, 'Demo NFS Strasbourg Archive', 'linux_file_server', 'nfs', 'nfs03.corp.demo', 2049, '/srv/archive', 'kerberos', NULL, NULL, JSON_OBJECT('acl_apply', false, 'probe', true), 'Archive endpoint', 'DEMO-ENDPOINT-NFS-STRASBOURG-ARCHIVE', 'OU=BornToShare-Strasbourg,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'success', UTC_TIMESTAMP() - INTERVAL 14 MINUTE, 'NFS probe succeeded', 1, 'active'),
  (@zone_rennes_id, @demo_ad_source_id, 'Demo SMB Rennes Sandbox', 'windows_file_server', 'smb', 'fs07.corp.demo', 445, '\\\\fs07\\sandbox', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs07-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Sandbox endpoint', 'DEMO-ENDPOINT-SMB-RENNES-SANDBOX', 'OU=BornToShare-Rennes,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'unknown', UTC_TIMESTAMP() - INTERVAL 3 HOUR, 'No fresh probe result yet', 1, 'maintenance'),
  (@zone_paris_id, @demo_ad_source_id, 'Demo SMB Paris Finance DR', 'windows_file_server', 'smb', 'fs08.corp.demo', 445, '\\\\fs08\\finance-dr', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs08-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Finance DR endpoint', 'DEMO-ENDPOINT-SMB-PARIS-FINANCE-DR', 'OU=BornToShare,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'success', UTC_TIMESTAMP() - INTERVAL 6 MINUTE, 'SMB probe succeeded', 1, 'active'),
  (@zone_lyon_id, @demo_ad_source_id, 'Demo SMB Lyon HR Archive', 'windows_file_server', 'smb', 'fs09.corp.demo', 445, '\\\\fs09\\hr-archive', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs09-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'HR archive endpoint', 'DEMO-ENDPOINT-SMB-LYON-HR-ARCHIVE', 'OU=BornToShare-Lyon,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'failed', UTC_TIMESTAMP() - INTERVAL 32 MINUTE, 'HR archive endpoint warning', 1, 'warning'),
  (@zone_marseille_id, @demo_ad_source_id, 'Demo NFS Marseille Engineering DR', 'linux_file_server', 'nfs', 'nfs04.corp.demo', 2049, '/srv/eng-dr', 'kerberos', NULL, NULL, JSON_OBJECT('acl_apply', false, 'probe', true), 'Engineering DR endpoint', 'DEMO-ENDPOINT-NFS-MARSEILLE-ENG-DR', 'OU=BornToShare-Marseille,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'success', UTC_TIMESTAMP() - INTERVAL 9 MINUTE, 'NFS probe succeeded', 1, 'active'),
  (@zone_nantes_id, @demo_ad_source_id, 'Demo SMB Nantes Legal DR', 'windows_file_server', 'smb', 'fs10.corp.demo', 445, '\\\\fs10\\legal-dr', 'ntlm', 'CORP\\svc-borntoshare', 'secret://demo/fs10-bind', JSON_OBJECT('acl_apply', true, 'probe', true), 'Legal DR endpoint', 'DEMO-ENDPOINT-SMB-NANTES-LEGAL-DR', 'OU=BornToShare-Nantes,OU=Groups,DC=corp,DC=demo', '{PREFIX}_{ROOTCODE}_{PERM}', 'running', UTC_TIMESTAMP() - INTERVAL 4 MINUTE, 'Probe currently running', 1, 'active');

SET @endpoint_lille_sales_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-LILLE-SALES' ORDER BY id DESC LIMIT 1);
SET @endpoint_bordeaux_ops_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-NFS-BORDEAUX-OPS' ORDER BY id DESC LIMIT 1);
SET @endpoint_toulouse_shared_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-TOULOUSE-SHARED' ORDER BY id DESC LIMIT 1);
SET @endpoint_nice_compliance_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-NICE-COMPLIANCE' ORDER BY id DESC LIMIT 1);
SET @endpoint_strasbourg_archive_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-NFS-STRASBOURG-ARCHIVE' ORDER BY id DESC LIMIT 1);
SET @endpoint_rennes_sandbox_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-RENNES-SANDBOX' ORDER BY id DESC LIMIT 1);
SET @endpoint_paris_finance_dr_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-PARIS-FINANCE-DR' ORDER BY id DESC LIMIT 1);
SET @endpoint_lyon_hr_archive_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-LYON-HR-ARCHIVE' ORDER BY id DESC LIMIT 1);
SET @endpoint_marseille_eng_dr_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-NFS-MARSEILLE-ENG-DR' ORDER BY id DESC LIMIT 1);
SET @endpoint_nantes_legal_dr_id := (SELECT id FROM storage_endpoints WHERE external_id = 'DEMO-ENDPOINT-SMB-NANTES-LEGAL-DR' ORDER BY id DESC LIMIT 1);

-- ------------------------------------------------------------
-- Large demo expansion: synthetic root estate across all demo
-- endpoints. The goal is to reach a realistic multi-year estate
-- without relying on external systems.
-- ------------------------------------------------------------

INSERT INTO storage_roots (
  storage_endpoint_id,
  parent_storage_root_id,
  name,
  root_path,
  normalized_root_path,
  inherit_owners,
  inherit_tags,
  status,
  last_probe_status,
  last_probe_at,
  last_probe_message,
  last_discovery_at,
  discovered_permissions_json,
  discovered_tree_json,
  needs_revalidation,
  revalidation_reason
)
SELECT
  em.endpoint_id,
  NULL AS parent_storage_root_id,
  CONCAT(em.family_label, ' ', rt.suffix_label) AS name,
  CASE
    WHEN rt.suffix_slug = '' THEN em.base_path
    ELSE CONCAT(em.base_path, CASE WHEN em.protocol = 'nfs' THEN '/' ELSE '\\\\' END, rt.suffix_slug)
  END AS root_path,
  CASE
    WHEN rt.suffix_slug = '' THEN em.base_norm
    ELSE CONCAT(em.base_norm, '/', rt.suffix_slug)
  END AS normalized_root_path,
  CASE WHEN rt.suffix_slug = '' THEN 0 ELSE 1 END AS inherit_owners,
  1 AS inherit_tags,
  rt.status,
  rt.probe_status,
  UTC_TIMESTAMP() - INTERVAL (10 + em.endpoint_ord * 5 + rt.template_ord) MINUTE AS last_probe_at,
  rt.probe_message,
  UTC_TIMESTAMP() - INTERVAL (10 + em.endpoint_ord * 5 + rt.template_ord) MINUTE AS last_discovery_at,
  JSON_OBJECT(
    'permissions',
    JSON_ARRAY(
      JSON_OBJECT('group', em.read_group, 'permission', 'READ'),
      JSON_OBJECT('group', em.write_group, 'permission', 'WRITE')
    ),
    'discovered_at',
    UTC_TIMESTAMP() - INTERVAL (10 + em.endpoint_ord * 5 + rt.template_ord) MINUTE
  ) AS discovered_permissions_json,
  CASE
    WHEN rt.suffix_slug = '' THEN JSON_OBJECT('children', JSON_ARRAY('shared', 'archive'))
    WHEN rt.suffix_slug = 'restricted' THEN JSON_OBJECT('children', JSON_ARRAY('reviews', 'exceptions'))
    WHEN rt.suffix_slug = 'temp' THEN JSON_OBJECT('children', JSON_ARRAY('scratch'))
    ELSE JSON_OBJECT('children', JSON_ARRAY())
  END AS discovered_tree_json,
  rt.needs_revalidation,
  rt.revalidation_reason
FROM (
  SELECT 1 AS endpoint_ord, @endpoint_paris_id AS endpoint_id, 'finance' AS family_key, 'Finance' AS family_label, 'smb' AS protocol, '\\\\fs01\\corp' AS base_path, '/corp/finance' AS base_norm, 'B2S_FINANCE_READ' AS read_group, 'B2S_FINANCE_WRITE' AS write_group
  UNION ALL SELECT 2, @endpoint_lyon_id, 'hr', 'HR', 'smb', '\\\\fs02\\corp', '/corp/hr', 'B2S_HR_READ', 'B2S_HR_WRITE'
  UNION ALL SELECT 3, @endpoint_marseille_id, 'engineering', 'Engineering', 'nfs', '/srv/shares/engineering', '/corp/engineering', 'B2S_ENG_READ', 'B2S_ENG_WRITE'
  UNION ALL SELECT 4, @endpoint_nantes_id, 'legal', 'Legal', 'smb', '\\\\fs03\\records', '/corp/legal', 'B2S_LEGAL_READ', 'B2S_LEGAL_WRITE'
  UNION ALL SELECT 5, @endpoint_paris_lab_id, 'sandbox', 'Sandbox', 'smb', '\\\\labfs01\\sandbox', '/corp/labs/sandbox', 'B2S_SANDBOX_READ', 'B2S_SANDBOX_WRITE'
  UNION ALL SELECT 6, @endpoint_lille_sales_id, 'sales', 'Sales', 'smb', '\\\\fs04\\sales', '/corp/sales', 'B2S_SALES_READ', 'B2S_SALES_WRITE'
  UNION ALL SELECT 7, @endpoint_bordeaux_ops_id, 'ops', 'Operations', 'nfs', '/srv/ops', '/corp/operations', 'B2S_OPS_READ', 'B2S_OPS_WRITE'
  UNION ALL SELECT 8, @endpoint_toulouse_shared_id, 'shared', 'Shared', 'smb', '\\\\fs05\\shared', '/corp/projects/shared', 'B2S_SHARED_READ', 'B2S_SHARED_WRITE'
  UNION ALL SELECT 9, @endpoint_nice_compliance_id, 'compliance', 'Compliance', 'smb', '\\\\fs06\\compliance', '/corp/compliance', 'B2S_COMPLIANCE_READ', 'B2S_COMPLIANCE_WRITE'
  UNION ALL SELECT 10, @endpoint_strasbourg_archive_id, 'archive', 'Archive', 'nfs', '/srv/archive', '/corp/archive', 'B2S_ARCHIVE_READ', 'B2S_ARCHIVE_WRITE'
  UNION ALL SELECT 11, @endpoint_rennes_sandbox_id, 'sandbox', 'Sandbox', 'smb', '\\\\fs07\\sandbox', '/corp/sandbox', 'B2S_SANDBOX_READ', 'B2S_SANDBOX_WRITE'
  UNION ALL SELECT 12, @endpoint_paris_finance_dr_id, 'finance-dr', 'Finance DR', 'smb', '\\\\fs08\\finance-dr', '/corp/finance-dr', 'B2S_FINANCE_READ', 'B2S_FINANCE_WRITE'
  UNION ALL SELECT 13, @endpoint_lyon_hr_archive_id, 'hr-archive', 'HR Archive', 'smb', '\\\\fs09\\hr-archive', '/corp/hr-archive', 'B2S_HR_READ', 'B2S_HR_WRITE'
  UNION ALL SELECT 14, @endpoint_marseille_eng_dr_id, 'engineering-dr', 'Engineering DR', 'nfs', '/srv/eng-dr', '/corp/engineering-dr', 'B2S_ENG_READ', 'B2S_ENG_WRITE'
  UNION ALL SELECT 15, @endpoint_nantes_legal_dr_id, 'legal-dr', 'Legal DR', 'smb', '\\\\fs10\\legal-dr', '/corp/legal-dr', 'B2S_LEGAL_READ', 'B2S_LEGAL_WRITE'
) em
CROSS JOIN (
  SELECT 1 AS template_ord, 'Main' AS suffix_label, 'main' AS suffix_slug, 'active' AS status, 'success' AS probe_status, 'Primary subtree is healthy' AS probe_message, 0 AS needs_revalidation, NULL AS revalidation_reason
  UNION ALL SELECT 2, 'Shared', 'shared', 'active', 'success', 'Shared subtree is available', 0, NULL
  UNION ALL SELECT 3, 'Archive', 'archive', 'active', 'success', 'Archive subtree is stable', 0, NULL
  UNION ALL SELECT 4, 'Restricted', 'restricted', 'warning', 'failed', 'Restricted subtree requires review', 1, 'Guardian approval pending'
  UNION ALL SELECT 5, 'Temp', 'temp', 'maintenance', 'running', 'Temporary subtree is under inspection', 1, 'Probe currently running'
) rt;

INSERT IGNORE INTO storage_root_roles (root_id, identity_id, role, assigned_by)
SELECT
  sr.id,
  CASE
    WHEN sr.normalized_root_path LIKE '/corp/finance-dr%' OR sr.normalized_root_path LIKE '/corp/finance%' THEN @identity_alice_id
    WHEN sr.normalized_root_path LIKE '/corp/hr-archive%' OR sr.normalized_root_path LIKE '/corp/hr%' THEN @identity_bob_id
    WHEN sr.normalized_root_path LIKE '/corp/engineering-dr%' OR sr.normalized_root_path LIKE '/corp/engineering%' THEN @identity_claire_id
    WHEN sr.normalized_root_path LIKE '/corp/legal-dr%' OR sr.normalized_root_path LIKE '/corp/legal%' THEN @identity_bob_id
    WHEN sr.normalized_root_path LIKE '/corp/projects/shared%' THEN @identity_support_id
    WHEN sr.normalized_root_path LIKE '/corp/compliance%' THEN @identity_claire_id
    WHEN sr.normalized_root_path LIKE '/corp/archive%' THEN @identity_admin_id
    WHEN sr.normalized_root_path LIKE '/corp/sales%' THEN @identity_alice_id
    WHEN sr.normalized_root_path LIKE '/corp/operations%' THEN @identity_claire_id
    WHEN sr.normalized_root_path LIKE '/corp/labs/sandbox%' OR sr.normalized_root_path LIKE '/corp/sandbox%' THEN @identity_support_id
    ELSE @identity_admin_id
  END AS identity_id,
  'guardian' AS role,
  @identity_admin_id AS assigned_by
FROM storage_roots sr
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
WHERE se.external_id LIKE 'DEMO-%';

INSERT IGNORE INTO storage_root_tags (storage_root_id, tag_id)
SELECT DISTINCT
  sr.id,
  CASE
    WHEN sr.normalized_root_path LIKE '/corp/finance-dr%' OR sr.normalized_root_path LIKE '/corp/finance%' THEN @tag_finance_id
    WHEN sr.normalized_root_path LIKE '/corp/hr-archive%' OR sr.normalized_root_path LIKE '/corp/hr%' THEN @tag_hr_id
    WHEN sr.normalized_root_path LIKE '/corp/engineering-dr%' OR sr.normalized_root_path LIKE '/corp/engineering%' THEN @tag_engineering_id
    WHEN sr.normalized_root_path LIKE '/corp/legal-dr%' OR sr.normalized_root_path LIKE '/corp/legal%' THEN @tag_legal_id
    WHEN sr.normalized_root_path LIKE '/corp/projects/shared%' THEN @tag_shared_id
    WHEN sr.normalized_root_path LIKE '/corp/compliance%' THEN @tag_pii_id
    WHEN sr.normalized_root_path LIKE '/corp/archive%' THEN @tag_critical_id
    WHEN sr.normalized_root_path LIKE '/corp/sales%' THEN @tag_shared_id
    WHEN sr.normalized_root_path LIKE '/corp/operations%' THEN @tag_critical_id
    WHEN sr.normalized_root_path LIKE '/corp/labs/sandbox%' OR sr.normalized_root_path LIKE '/corp/sandbox%' THEN @tag_sandbox_id
    ELSE @tag_shared_id
  END AS tag_id
FROM storage_roots sr
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
WHERE se.external_id LIKE 'DEMO-%';

-- ------------------------------------------------------------
-- Access request lifecycle: pending, approved, rejected,
-- executed, failed and revoked.
-- ------------------------------------------------------------

INSERT INTO access_requests (
  code,
  requester_identity_id,
  status,
  decision_comment,
  decided_at,
  revoked_at,
  directory_snapshot_id,
  context_snapshot_at,
  requested_principal_json,
  created_at,
  updated_at
)
VALUES
  ('DEMO-AR-PENDING-001', @identity_alice_id, 'pending', 'Need temporary AP read access for month-end close.', NULL, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 2 HOUR, JSON_OBJECT('type', 'user', 'external_id', 'U-ALICE', 'username', 'alice.finance', 'display_name', 'Alice Finance', 'dn', 'CN=Alice Finance,OU=Finance,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 2 HOUR, UTC_TIMESTAMP() - INTERVAL 2 HOUR),
  ('DEMO-AR-PENDING-002', @identity_alice_id, 'pending', 'Need write access to Engineering Builds for the next release window.', NULL, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 80 MINUTE, JSON_OBJECT('type', 'user', 'external_id', 'U-ALICE', 'username', 'alice.finance', 'display_name', 'Alice Finance', 'dn', 'CN=Alice Finance,OU=Finance,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 80 MINUTE, UTC_TIMESTAMP() - INTERVAL 80 MINUTE),
  ('DEMO-AR-PENDING-003', @identity_claire_id, 'pending', 'Need temporary read access to Lab Sandbox for validation.', NULL, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 25 MINUTE, JSON_OBJECT('type', 'user', 'external_id', 'U-CLAIRE', 'username', 'claire.audit', 'display_name', 'Claire Auditor', 'dn', 'CN=Claire Auditor,OU=IT,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 25 MINUTE, UTC_TIMESTAMP() - INTERVAL 25 MINUTE),
  ('DEMO-AR-APPROVED-001', @identity_bob_id, 'approved', 'Approved by HR guardian; provisioning is running.', UTC_TIMESTAMP() - INTERVAL 50 MINUTE, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 1 HOUR, JSON_OBJECT('type', 'user', 'external_id', 'U-BOB', 'username', 'bob.hr', 'display_name', 'Bob HR', 'dn', 'CN=Bob HR,OU=HR,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 1 HOUR, UTC_TIMESTAMP() - INTERVAL 50 MINUTE),
  ('DEMO-AR-APPROVED-002', @identity_claire_id, 'approved', 'Approved by legal owner; enforcement still running.', UTC_TIMESTAMP() - INTERVAL 12 MINUTE, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 20 MINUTE, JSON_OBJECT('type', 'user', 'external_id', 'U-CLAIRE', 'username', 'claire.audit', 'display_name', 'Claire Auditor', 'dn', 'CN=Claire Auditor,OU=IT,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 20 MINUTE, UTC_TIMESTAMP() - INTERVAL 12 MINUTE),
  ('DEMO-AR-REJECTED-001', @identity_diego_id, 'rejected', 'Rejected: contractor account is disabled in directory snapshot.', UTC_TIMESTAMP() - INTERVAL 90 MINUTE, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 2 HOUR, JSON_OBJECT('type', 'user', 'external_id', 'U-DIEGO', 'username', 'diego.contractor', 'display_name', 'Diego Contractor', 'dn', 'CN=Diego Contractor,OU=Finance,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 2 HOUR, UTC_TIMESTAMP() - INTERVAL 90 MINUTE),
  ('DEMO-AR-REJECTED-002', @identity_diego_id, 'rejected', 'Rejected: sandbox access is not allowed for disabled users.', UTC_TIMESTAMP() - INTERVAL 15 MINUTE, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 18 MINUTE, JSON_OBJECT('type', 'user', 'external_id', 'U-DIEGO', 'username', 'diego.contractor', 'display_name', 'Diego Contractor', 'dn', 'CN=Diego Contractor,OU=Finance,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 18 MINUTE, UTC_TIMESTAMP() - INTERVAL 15 MINUTE),
  ('DEMO-AR-EXECUTED-001', @identity_claire_id, 'executed', 'Approved and enforced for audit review.', UTC_TIMESTAMP() - INTERVAL 3 DAY, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 3 DAY, JSON_OBJECT('type', 'user', 'external_id', 'U-CLAIRE', 'username', 'claire.audit', 'display_name', 'Claire Auditor', 'dn', 'CN=Claire Auditor,OU=IT,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 3 DAY, UTC_TIMESTAMP() - INTERVAL 3 DAY + INTERVAL 10 MINUTE),
  ('DEMO-AR-EXECUTED-002', @identity_bob_id, 'executed', 'Shared Projects access granted and verified.', UTC_TIMESTAMP() - INTERVAL 6 HOUR, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 7 HOUR, JSON_OBJECT('type', 'user', 'external_id', 'U-BOB', 'username', 'bob.hr', 'display_name', 'Bob HR', 'dn', 'CN=Bob HR,OU=HR,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 7 HOUR, UTC_TIMESTAMP() - INTERVAL 6 HOUR),
  ('DEMO-AR-FAILED-001', @identity_alice_id, 'failed', 'Approval was granted but provisioning failed on HR write group.', UTC_TIMESTAMP() - INTERVAL 30 MINUTE, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 45 MINUTE, JSON_OBJECT('type', 'user', 'external_id', 'U-ALICE', 'username', 'alice.finance', 'display_name', 'Alice Finance', 'dn', 'CN=Alice Finance,OU=Finance,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 45 MINUTE, UTC_TIMESTAMP() - INTERVAL 30 MINUTE),
  ('DEMO-AR-FAILED-002', @identity_bob_id, 'failed', 'Shared Projects write request failed because target group is retrying.', UTC_TIMESTAMP() - INTERVAL 55 MINUTE, NULL, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 70 MINUTE, JSON_OBJECT('type', 'user', 'external_id', 'U-BOB', 'username', 'bob.hr', 'display_name', 'Bob HR', 'dn', 'CN=Bob HR,OU=HR,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 70 MINUTE, UTC_TIMESTAMP() - INTERVAL 55 MINUTE),
  ('DEMO-AR-REVOKED-001', @identity_bob_id, 'revoked', 'Access removed after transfer to another team.', UTC_TIMESTAMP() - INTERVAL 8 DAY, UTC_TIMESTAMP() - INTERVAL 1 DAY, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 10 DAY, JSON_OBJECT('type', 'user', 'external_id', 'U-BOB', 'username', 'bob.hr', 'display_name', 'Bob HR', 'dn', 'CN=Bob HR,OU=HR,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 10 DAY, UTC_TIMESTAMP() - INTERVAL 1 DAY),
  ('DEMO-AR-REVOKED-002', @identity_alice_id, 'revoked', 'Legal access revoked after review completion.', UTC_TIMESTAMP() - INTERVAL 12 DAY, UTC_TIMESTAMP() - INTERVAL 2 DAY, @snapshot_active_id, UTC_TIMESTAMP() - INTERVAL 14 DAY, JSON_OBJECT('type', 'user', 'external_id', 'U-ALICE', 'username', 'alice.finance', 'display_name', 'Alice Finance', 'dn', 'CN=Alice Finance,OU=Finance,DC=corp,DC=demo'), UTC_TIMESTAMP() - INTERVAL 14 DAY, UTC_TIMESTAMP() - INTERVAL 2 DAY),
  ('DEMO-AR-EXPIRED-001', @identity_jdupont_id, 'expired', 'Temporary Finance access was granted for a short window and is now expired.', UTC_TIMESTAMP() - INTERVAL 2 DAY, NULL, @snapshot_openldap_id, UTC_TIMESTAMP() - INTERVAL 5 DAY, JSON_OBJECT('type', 'user', 'external_id', 'U-JDUPONT', 'username', 'jdupont', 'display_name', 'Jean Dupont', 'dn', 'uid=jdupont,ou=people,dc=ldap,dc=demo'), UTC_TIMESTAMP() - INTERVAL 5 DAY, UTC_TIMESTAMP() - INTERVAL 2 DAY);

SET @ar_pending_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-PENDING-001' LIMIT 1);
SET @ar_pending_2_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-PENDING-002' LIMIT 1);
SET @ar_pending_3_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-PENDING-003' LIMIT 1);
SET @ar_approved_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-APPROVED-001' LIMIT 1);
SET @ar_approved_2_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-APPROVED-002' LIMIT 1);
SET @ar_rejected_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-REJECTED-001' LIMIT 1);
SET @ar_rejected_2_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-REJECTED-002' LIMIT 1);
SET @ar_executed_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-EXECUTED-001' LIMIT 1);
SET @ar_executed_2_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-EXECUTED-002' LIMIT 1);
SET @ar_failed_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-FAILED-001' LIMIT 1);
SET @ar_failed_2_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-FAILED-002' LIMIT 1);
SET @ar_revoked_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-REVOKED-001' LIMIT 1);
SET @ar_revoked_2_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-REVOKED-002' LIMIT 1);
SET @ar_expired_id := (SELECT id FROM access_requests WHERE code = 'DEMO-AR-EXPIRED-001' LIMIT 1);

INSERT INTO access_request_items (access_request_id, target_type, target_id, permission, expires_at)
VALUES
  (@ar_pending_id, 'storage_root', @root_fin_ap_id, 'read', UTC_TIMESTAMP() + INTERVAL 14 DAY),
  (@ar_pending_2_id, 'storage_root', @root_eng_builds_id, 'write', UTC_TIMESTAMP() + INTERVAL 5 DAY),
  (@ar_pending_3_id, 'storage_root', @root_lab_id, 'read', UTC_TIMESTAMP() + INTERVAL 2 DAY),
  (@ar_approved_id, 'storage_root', @root_hr_onboarding_id, 'read', UTC_TIMESTAMP() + INTERVAL 20 DAY),
  (@ar_approved_2_id, 'storage_root', @root_legal_contracts_id, 'read', UTC_TIMESTAMP() + INTERVAL 30 DAY),
  (@ar_rejected_id, 'storage_root', @root_finance_id, 'write', NULL),
  (@ar_rejected_2_id, 'storage_root', @root_lab_id, 'read', NULL),
  (@ar_executed_id, 'storage_root', @root_finance_id, 'read', UTC_TIMESTAMP() + INTERVAL 60 DAY),
  (@ar_executed_2_id, 'storage_root', @root_shared_id, 'read', UTC_TIMESTAMP() + INTERVAL 45 DAY),
  (@ar_failed_id, 'storage_root', @root_hr_id, 'write', UTC_TIMESTAMP() + INTERVAL 7 DAY),
  (@ar_failed_2_id, 'storage_root', @root_shared_id, 'write', UTC_TIMESTAMP() + INTERVAL 10 DAY),
  (@ar_revoked_id, 'storage_root', @root_finance_id, 'read', UTC_TIMESTAMP() - INTERVAL 1 DAY),
  (@ar_revoked_2_id, 'storage_root', @root_legal_id, 'read', UTC_TIMESTAMP() - INTERVAL 2 DAY),
  (@ar_expired_id, 'storage_root', @root_finance_id, 'read', UTC_TIMESTAMP() - INTERVAL 2 DAY);

SET @ari_pending_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_pending_id LIMIT 1);
SET @ari_pending_2_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_pending_2_id LIMIT 1);
SET @ari_pending_3_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_pending_3_id LIMIT 1);
SET @ari_approved_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_approved_id LIMIT 1);
SET @ari_approved_2_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_approved_2_id LIMIT 1);
SET @ari_executed_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_executed_id LIMIT 1);
SET @ari_executed_2_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_executed_2_id LIMIT 1);
SET @ari_failed_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_failed_id LIMIT 1);
SET @ari_failed_2_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_failed_2_id LIMIT 1);
SET @ari_revoked_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_revoked_id LIMIT 1);
SET @ari_revoked_2_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_revoked_2_id LIMIT 1);
SET @ari_expired_id := (SELECT id FROM access_request_items WHERE access_request_id = @ar_expired_id LIMIT 1);

INSERT INTO access_request_item_executions (
  access_request_id,
  access_request_item_id,
  status,
  error_message,
  requested_payload_json,
  result_json,
  started_at,
  finished_at
)
VALUES
  (@ar_pending_id, @ari_pending_id, 'PENDING', NULL, JSON_OBJECT('access_level', 'read'), JSON_OBJECT(), NULL, NULL),
  (@ar_pending_2_id, @ari_pending_2_id, 'PENDING', NULL, JSON_OBJECT('access_level', 'write'), JSON_OBJECT(), NULL, NULL),
  (@ar_pending_3_id, @ari_pending_3_id, 'PENDING', NULL, JSON_OBJECT('access_level', 'read'), JSON_OBJECT(), NULL, NULL),
  (@ar_approved_id, @ari_approved_id, 'RUNNING', NULL, JSON_OBJECT('access_level', 'read', 'target_group', 'B2S_HR_READ'), JSON_OBJECT('job', 'membership_update'), UTC_TIMESTAMP() - INTERVAL 45 MINUTE, NULL),
  (@ar_approved_2_id, @ari_approved_2_id, 'RUNNING', NULL, JSON_OBJECT('access_level', 'read', 'target_group', 'B2S_LEGAL_READ'), JSON_OBJECT('job', 'membership_update'), UTC_TIMESTAMP() - INTERVAL 10 MINUTE, NULL),
  (@ar_executed_id, @ari_executed_id, 'DONE', NULL, JSON_OBJECT('access_level', 'read', 'target_group', 'B2S_FINANCE_READ'), JSON_OBJECT('membership_added', true), UTC_TIMESTAMP() - INTERVAL 3 DAY + INTERVAL 2 MINUTE, UTC_TIMESTAMP() - INTERVAL 3 DAY + INTERVAL 10 MINUTE),
  (@ar_executed_2_id, @ari_executed_2_id, 'DONE', NULL, JSON_OBJECT('access_level', 'read', 'target_group', 'B2S_SHARED_READ'), JSON_OBJECT('membership_added', true), UTC_TIMESTAMP() - INTERVAL 6 HOUR + INTERVAL 2 MINUTE, UTC_TIMESTAMP() - INTERVAL 6 HOUR + INTERVAL 8 MINUTE),
  (@ar_failed_id, @ari_failed_id, 'FAILED', 'AD group B2S_HR_WRITE is missing; provisioning failed.', JSON_OBJECT('access_level', 'write', 'target_group', 'B2S_HR_WRITE'), JSON_OBJECT('membership_added', false), UTC_TIMESTAMP() - INTERVAL 28 MINUTE, UTC_TIMESTAMP() - INTERVAL 25 MINUTE),
  (@ar_failed_2_id, @ari_failed_2_id, 'FAILED', 'Shared write group is still retrying after ACL drift.', JSON_OBJECT('access_level', 'write', 'target_group', 'B2S_SHARED_WRITE'), JSON_OBJECT('membership_added', false), UTC_TIMESTAMP() - INTERVAL 52 MINUTE, UTC_TIMESTAMP() - INTERVAL 48 MINUTE),
  (@ar_revoked_id, @ari_revoked_id, 'DONE', NULL, JSON_OBJECT('access_level', 'read', 'target_group', 'B2S_FINANCE_READ', 'operation', 'revoke'), JSON_OBJECT('membership_removed', true), UTC_TIMESTAMP() - INTERVAL 1 DAY, UTC_TIMESTAMP() - INTERVAL 1 DAY + INTERVAL 5 MINUTE),
  (@ar_revoked_2_id, @ari_revoked_2_id, 'DONE', NULL, JSON_OBJECT('access_level', 'read', 'target_group', 'B2S_LEGAL_READ', 'operation', 'revoke'), JSON_OBJECT('membership_removed', true), UTC_TIMESTAMP() - INTERVAL 2 DAY, UTC_TIMESTAMP() - INTERVAL 2 DAY + INTERVAL 3 MINUTE),
  (@ar_expired_id, @ari_expired_id, 'DONE', NULL, JSON_OBJECT('access_level', 'read', 'target_group', 'B2S_FINANCE_READ', 'operation', 'expire'), JSON_OBJECT('membership_expired', true), UTC_TIMESTAMP() - INTERVAL 2 DAY, UTC_TIMESTAMP() - INTERVAL 2 DAY + INTERVAL 2 MINUTE);

-- ------------------------------------------------------------
-- Provisioning jobs, governance events, alerts and health.
-- ------------------------------------------------------------

INSERT INTO provisioning_jobs (
  correlation_id,
  job_type,
  action,
  status,
  storage_root_access_profile_id,
  identity_source_id,
  payload_json,
  result_json,
  metrics_json,
  error_json,
  error_code,
  error_message,
  started_at,
  finished_at
)
VALUES
  ('demo-provisioning-queued', 'AD_GROUP_ENSURE', 'ensure_ad_group', 'QUEUED', @srap_hr_write_id, @demo_ad_source_id, JSON_OBJECT('group', 'B2S_HR_WRITE'), JSON_OBJECT(), JSON_OBJECT('submitted_by', 'seed'), JSON_OBJECT(), NULL, NULL, NULL, NULL),
  ('demo-provisioning-running', 'ACL_APPLY', 'acl_apply_via_group', 'RUNNING', @srap_hr_read_id, @demo_ad_source_id, JSON_OBJECT('root_id', @root_hr_id, 'group', 'B2S_HR_READ'), JSON_OBJECT(), JSON_OBJECT('progress', 42), JSON_OBJECT(), NULL, NULL, UTC_TIMESTAMP() - INTERVAL 45 MINUTE, NULL),
  ('demo-provisioning-succeeded', 'ACL_APPLY', 'acl_apply_via_group', 'SUCCEEDED', @srap_fin_read_id, @demo_ad_source_id, JSON_OBJECT('root_id', @root_finance_id, 'group', 'B2S_FINANCE_READ'), JSON_OBJECT('acl_applied', true), JSON_OBJECT('duration_ms', 2100), JSON_OBJECT(), NULL, NULL, UTC_TIMESTAMP() - INTERVAL 3 DAY + INTERVAL 2 MINUTE, UTC_TIMESTAMP() - INTERVAL 3 DAY + INTERVAL 10 MINUTE),
  ('demo-provisioning-failed', 'AD_GROUP_ENSURE', 'ensure_ad_group', 'FAILED', @srap_hr_write_id, @demo_ad_source_id, JSON_OBJECT('group', 'B2S_HR_WRITE'), JSON_OBJECT('group_created', false), JSON_OBJECT('duration_ms', 1800), JSON_OBJECT('code', 'AD_GROUP_CREATE_FAILED'), 'AD_GROUP_CREATE_FAILED', 'Demo failure creating write group.', UTC_TIMESTAMP() - INTERVAL 28 MINUTE, UTC_TIMESTAMP() - INTERVAL 25 MINUTE),
  ('demo-provisioning-cancelled', 'SMB_PROBE', 'test_smb_ntlm', 'CANCELLED', NULL, @demo_ad_source_id, JSON_OBJECT('endpoint_id', @endpoint_lyon_id), JSON_OBJECT(), JSON_OBJECT('cancelled_by', 'demo-seed'), JSON_OBJECT(), 'USER_CANCELLED', 'Synthetic cancelled probe.', UTC_TIMESTAMP() - INTERVAL 1 DAY, UTC_TIMESTAMP() - INTERVAL 1 DAY + INTERVAL 2 MINUTE),
  ('demo-provisioning-running-legal', 'ACL_APPLY', 'acl_apply_via_group', 'RUNNING', @srap_legal_read_id, @demo_ad_source_id, JSON_OBJECT('root_id', @root_legal_id, 'group', 'B2S_LEGAL_READ'), JSON_OBJECT(), JSON_OBJECT('progress', 65), JSON_OBJECT(), NULL, NULL, UTC_TIMESTAMP() - INTERVAL 10 MINUTE, NULL),
  ('demo-provisioning-succeeded-shared', 'ACL_APPLY', 'acl_apply_via_group', 'SUCCEEDED', @srap_shared_read_id, @demo_ad_source_id, JSON_OBJECT('root_id', @root_shared_id, 'group', 'B2S_SHARED_READ'), JSON_OBJECT('acl_applied', true), JSON_OBJECT('duration_ms', 1450), JSON_OBJECT(), NULL, NULL, UTC_TIMESTAMP() - INTERVAL 6 HOUR + INTERVAL 2 MINUTE, UTC_TIMESTAMP() - INTERVAL 6 HOUR + INTERVAL 8 MINUTE),
  ('demo-provisioning-retrying-shared-write', 'ACL_APPLY', 'acl_apply_via_group', 'RUNNING', @srap_shared_write_id, @demo_ad_source_id, JSON_OBJECT('root_id', @root_shared_id, 'group', 'B2S_SHARED_WRITE'), JSON_OBJECT('retry', 2), JSON_OBJECT('progress', 15), JSON_OBJECT(), NULL, NULL, UTC_TIMESTAMP() - INTERVAL 55 MINUTE, NULL),
  ('demo-provisioning-queued-lab', 'AD_GROUP_ENSURE', 'ensure_ad_group', 'QUEUED', @srap_lab_read_id, @demo_ad_source_id, JSON_OBJECT('root_id', @root_lab_id, 'group', 'B2S_LAB_READ'), JSON_OBJECT(), JSON_OBJECT('submitted_by', 'seed', 'priority', 'low'), JSON_OBJECT(), NULL, NULL, NULL, NULL)
ON DUPLICATE KEY UPDATE
  job_type = VALUES(job_type),
  action = VALUES(action),
  status = VALUES(status),
  storage_root_access_profile_id = VALUES(storage_root_access_profile_id),
  identity_source_id = VALUES(identity_source_id),
  payload_json = VALUES(payload_json),
  result_json = VALUES(result_json),
  metrics_json = VALUES(metrics_json),
  error_json = VALUES(error_json),
  error_code = VALUES(error_code),
  error_message = VALUES(error_message),
  started_at = VALUES(started_at),
  finished_at = VALUES(finished_at);

SET @job_running_id := (SELECT id FROM provisioning_jobs WHERE correlation_id = 'demo-provisioning-running' LIMIT 1);
SET @job_succeeded_id := (SELECT id FROM provisioning_jobs WHERE correlation_id = 'demo-provisioning-succeeded' LIMIT 1);
SET @job_failed_id := (SELECT id FROM provisioning_jobs WHERE correlation_id = 'demo-provisioning-failed' LIMIT 1);
SET @job_running_legal_id := (SELECT id FROM provisioning_jobs WHERE correlation_id = 'demo-provisioning-running-legal' LIMIT 1);
SET @job_succeeded_shared_id := (SELECT id FROM provisioning_jobs WHERE correlation_id = 'demo-provisioning-succeeded-shared' LIMIT 1);
SET @job_retrying_shared_write_id := (SELECT id FROM provisioning_jobs WHERE correlation_id = 'demo-provisioning-retrying-shared-write' LIMIT 1);
SET @job_queued_lab_id := (SELECT id FROM provisioning_jobs WHERE correlation_id = 'demo-provisioning-queued-lab' LIMIT 1);

INSERT INTO governance_events (
  event_type,
  target_type,
  target_id,
  storage_root_access_profile_id,
  provisioning_job_id,
  status,
  payload_json,
  prev_hash,
  event_hash,
  actor_ip,
  user_agent,
  created_at
)
VALUES
  ('access_request.created', 'access_request', @ar_pending_id, NULL, NULL, 'pending', JSON_OBJECT('code', 'DEMO-AR-PENDING-001'), NULL, SHA2('demo-governance-submit', 256), '127.0.0.1', 'demo-seed', UTC_TIMESTAMP() - INTERVAL 2 HOUR),
  ('access_request.approved', 'access_request', @ar_approved_id, NULL, NULL, 'approved', JSON_OBJECT('code', 'DEMO-AR-APPROVED-001'), SHA2('demo-governance-submit', 256), SHA2('demo-governance-approve', 256), '127.0.0.1', 'demo-seed', UTC_TIMESTAMP() - INTERVAL 50 MINUTE),
  ('provisioning.succeeded', 'storage_root_access_profile', @srap_fin_read_id, @srap_fin_read_id, @job_succeeded_id, 'SUCCEEDED', JSON_OBJECT('group', 'B2S_FINANCE_READ'), SHA2('demo-governance-approve', 256), SHA2('demo-governance-provision-ok', 256), '127.0.0.1', 'demo-seed', UTC_TIMESTAMP() - INTERVAL 3 DAY + INTERVAL 10 MINUTE),
  ('provisioning.failed', 'storage_root_access_profile', @srap_hr_write_id, @srap_hr_write_id, @job_failed_id, 'FAILED', JSON_OBJECT('group', 'B2S_HR_WRITE', 'error_code', 'AD_GROUP_CREATE_FAILED'), SHA2('demo-governance-provision-ok', 256), SHA2('demo-governance-provision-failed', 256), '127.0.0.1', 'demo-seed', UTC_TIMESTAMP() - INTERVAL 25 MINUTE),
  ('access_request.revoked', 'access_request', @ar_revoked_id, @srap_fin_read_id, NULL, 'revoked', JSON_OBJECT('code', 'DEMO-AR-REVOKED-001'), SHA2('demo-governance-provision-failed', 256), SHA2('demo-governance-revoke', 256), '127.0.0.1', 'demo-seed', UTC_TIMESTAMP() - INTERVAL 1 DAY),
  ('access_request.created', 'access_request', @ar_pending_2_id, @srap_eng_write_id, NULL, 'pending', JSON_OBJECT('code', 'DEMO-AR-PENDING-002'), NULL, SHA2('demo-governance-submit-2', 256), '127.0.0.1', 'demo-seed', UTC_TIMESTAMP() - INTERVAL 80 MINUTE),
  ('provisioning.succeeded', 'storage_root_access_profile', @srap_shared_read_id, @srap_shared_read_id, @job_succeeded_shared_id, 'SUCCEEDED', JSON_OBJECT('group', 'B2S_SHARED_READ'), SHA2('demo-governance-submit-2', 256), SHA2('demo-governance-provision-ok-2', 256), '127.0.0.1', 'demo-seed', UTC_TIMESTAMP() - INTERVAL 6 HOUR + INTERVAL 8 MINUTE),
  ('provisioning.running', 'storage_root_access_profile', @srap_legal_read_id, @srap_legal_read_id, @job_running_legal_id, 'RUNNING', JSON_OBJECT('group', 'B2S_LEGAL_READ'), SHA2('demo-governance-provision-ok-2', 256), SHA2('demo-governance-running-legal', 256), '127.0.0.1', 'demo-seed', UTC_TIMESTAMP() - INTERVAL 10 MINUTE);

INSERT INTO governance_alerts (
  alert_key,
  scope_type,
  scope_id,
  alert_type,
  severity,
  status,
  title,
  message,
  source_type,
  source_id,
  zone_id,
  storage_endpoint_id,
  storage_root_id,
  identity_source_id,
  correlation_id,
  first_seen_at,
  last_seen_at,
  resolved_at,
  acknowledged_at,
  acknowledged_by,
  metadata_json
)
VALUES
  ('demo.storage_root.hr.write_group_failed', 'storage_root', @root_hr_id, 'provisioning_failed', 'critical', 'open', 'HR write group provisioning failed', 'The WRITE governed group for HR could not be created.', 'provisioning_job', 'demo-provisioning-failed', @zone_lyon_id, @endpoint_lyon_id, @root_hr_id, @demo_ad_source_id, 'demo-provisioning-failed', UTC_TIMESTAMP() - INTERVAL 25 MINUTE, UTC_TIMESTAMP() - INTERVAL 25 MINUTE, NULL, NULL, NULL, JSON_OBJECT('error_code', 'AD_GROUP_CREATE_FAILED')),
  ('demo.storage_endpoint.lyon.probe_warning', 'storage_endpoint', @endpoint_lyon_id, 'probe_warning', 'warning', 'acknowledged', 'Lyon endpoint probe warning', 'Latency is above the expected threshold.', 'probe', 'demo-provisioning-cancelled', @zone_lyon_id, @endpoint_lyon_id, NULL, @demo_ad_source_id, 'demo-provisioning-cancelled', UTC_TIMESTAMP() - INTERVAL 1 DAY, UTC_TIMESTAMP() - INTERVAL 35 MINUTE, NULL, UTC_TIMESTAMP() - INTERVAL 30 MINUTE, @identity_admin_id, JSON_OBJECT('latency_ms', 1250)),
  ('demo.storage_root.finance.resolved_acl', 'storage_root', @root_finance_id, 'acl_drift', 'info', 'resolved', 'Finance ACL drift resolved', 'A previous ACL drift alert was reconciled.', 'reconciliation', 'demo-provisioning-succeeded', @zone_paris_id, @endpoint_paris_id, @root_finance_id, @demo_ad_source_id, 'demo-provisioning-succeeded', UTC_TIMESTAMP() - INTERVAL 4 DAY, UTC_TIMESTAMP() - INTERVAL 3 DAY, UTC_TIMESTAMP() - INTERVAL 3 DAY, NULL, NULL, JSON_OBJECT('resolved_by_job_id', @job_succeeded_id)),
  ('demo.identity_source.snapshot_stale', 'identity_source', @demo_ad_source_id, 'snapshot_stale', 'warning', 'open', 'Snapshot freshness warning', 'The AD snapshot is demo data and should be refreshed in a real environment.', 'snapshot', 'demo-directory-snapshot-active', NULL, NULL, NULL, @demo_ad_source_id, 'demo-directory-snapshot-active', UTC_TIMESTAMP() - INTERVAL 2 HOUR, UTC_TIMESTAMP() - INTERVAL 10 MINUTE, NULL, NULL, NULL, JSON_OBJECT('snapshot_version', 7)),
  ('demo.storage_root.shared.retrying_write', 'storage_root', @root_shared_id, 'provisioning_retry', 'warning', 'open', 'Shared Projects write provisioning is retrying', 'The WRITE governed group is still being reconciled.', 'provisioning_job', 'demo-provisioning-retrying-shared-write', @zone_marseille_id, @endpoint_marseille_id, @root_shared_id, @demo_ad_source_id, 'demo-provisioning-retrying-shared-write', UTC_TIMESTAMP() - INTERVAL 55 MINUTE, UTC_TIMESTAMP() - INTERVAL 5 MINUTE, NULL, NULL, NULL, JSON_OBJECT('retry_count', 2)),
  ('demo.storage_endpoint.nantes.running_probe', 'storage_endpoint', @endpoint_nantes_id, 'probe_running', 'info', 'open', 'Nantes endpoint probe in progress', 'The endpoint probe is still running.', 'probe', 'demo-provisioning-running-legal', @zone_nantes_id, @endpoint_nantes_id, NULL, @demo_ad_source_id, 'demo-provisioning-running-legal', UTC_TIMESTAMP() - INTERVAL 12 MINUTE, UTC_TIMESTAMP() - INTERVAL 2 MINUTE, NULL, NULL, NULL, JSON_OBJECT('job_id', @job_running_legal_id)),
  ('demo.storage_root.lab.pending_group', 'storage_root', @root_lab_id, 'group_pending', 'warning', 'open', 'Lab Sandbox group creation pending', 'The lab read group has not been provisioned yet.', 'provisioning_job', 'demo-provisioning-queued-lab', @zone_paris_id, @endpoint_paris_lab_id, @root_lab_id, @demo_ad_source_id, 'demo-provisioning-queued-lab', UTC_TIMESTAMP() - INTERVAL 25 MINUTE, UTC_TIMESTAMP() - INTERVAL 25 MINUTE, NULL, NULL, NULL, JSON_OBJECT('expected_group', 'B2S_LAB_READ')),
  ('demo.access_request.finance.approval_pending', 'access_request', @ar_pending_id, 'approval_pending', 'warning', 'open', 'Finance approval pending', 'Temporary Finance access is waiting for owner approval.', 'access_request', 'DEMO-AR-PENDING-001', NULL, NULL, @root_finance_id, @demo_openldap_source_id, 'DEMO-AR-PENDING-001', UTC_TIMESTAMP() - INTERVAL 2 HOUR, UTC_TIMESTAMP() - INTERVAL 2 HOUR, NULL, NULL, NULL, JSON_OBJECT('requester', 'alice.finance', 'target_group', 'FINANCE_RO')),
  ('demo.storage_root.finance.scan_failed', 'storage_root', @root_finance_id, 'scan_failed', 'critical', 'open', 'Finance ACL scan failed', 'The latest ACL discovery run for Finance stopped with an error.', 'acl_scan', 'demo-acl-scan-finance-failed', @zone_paris_id, @endpoint_paris_id, @root_finance_id, @demo_ad_source_id, 'demo-acl-scan-finance-failed', UTC_TIMESTAMP() - INTERVAL 40 MINUTE, UTC_TIMESTAMP() - INTERVAL 40 MINUTE, NULL, NULL, NULL, JSON_OBJECT('error_code', 'ACL_SCAN_TIMEOUT', 'attempt', 3)),
  ('demo.identity_source.openldap.sync_completed', 'identity_source', @demo_openldap_source_id, 'sync_completed', 'info', 'resolved', 'OpenLDAP sync completed', 'The OpenLDAP demo directory finished synchronizing successfully.', 'sync', 'demo-openldap-sync-completed', NULL, NULL, NULL, @demo_openldap_source_id, 'demo-openldap-sync-completed', UTC_TIMESTAMP() - INTERVAL 30 MINUTE, UTC_TIMESTAMP() - INTERVAL 30 MINUTE, UTC_TIMESTAMP() - INTERVAL 28 MINUTE, NULL, NULL, JSON_OBJECT('snapshot_version', 1, 'users', 5, 'groups', 6)),
  ('demo.storage_root.shared.new_owner_detected', 'storage_root', @root_shared_id, 'owner_detected', 'info', 'acknowledged', 'New owner detected on Shared Projects', 'Governance discovered a new primary owner for the shared root.', 'reconciliation', 'demo-shared-owner-detected', @zone_marseille_id, @endpoint_marseille_id, @root_shared_id, @demo_ad_source_id, 'demo-shared-owner-detected', UTC_TIMESTAMP() - INTERVAL 18 MINUTE, UTC_TIMESTAMP() - INTERVAL 18 MINUTE, NULL, UTC_TIMESTAMP() - INTERVAL 12 MINUTE, @identity_admin_id, JSON_OBJECT('owner_identity', 'U-CLAIRE', 'ownership_source', 'storage_root_roles'))
ON DUPLICATE KEY UPDATE
  scope_type = VALUES(scope_type),
  scope_id = VALUES(scope_id),
  alert_type = VALUES(alert_type),
  severity = VALUES(severity),
  status = VALUES(status),
  title = VALUES(title),
  message = VALUES(message),
  source_type = VALUES(source_type),
  source_id = VALUES(source_id),
  zone_id = VALUES(zone_id),
  storage_endpoint_id = VALUES(storage_endpoint_id),
  storage_root_id = VALUES(storage_root_id),
  identity_source_id = VALUES(identity_source_id),
  correlation_id = VALUES(correlation_id),
  first_seen_at = VALUES(first_seen_at),
  last_seen_at = VALUES(last_seen_at),
  resolved_at = VALUES(resolved_at),
  acknowledged_at = VALUES(acknowledged_at),
  acknowledged_by = VALUES(acknowledged_by),
  metadata_json = VALUES(metadata_json);

INSERT INTO governance_health_events (
  entity_type,
  entity_id,
  check_type,
  status,
  severity,
  message,
  source_type,
  source_id,
  job_id,
  correlation_id,
  checked_at,
  metadata_json
)
VALUES
  ('storage_endpoint', @endpoint_paris_id, 'probe', 'success', 'info', 'SMB probe succeeded.', 'probe', 'demo-provisioning-succeeded', @job_succeeded_id, 'demo-health-endpoint-paris', UTC_TIMESTAMP() - INTERVAL 5 MINUTE, JSON_OBJECT('latency_ms', 64)),
  ('storage_endpoint', @endpoint_lyon_id, 'probe', 'warning', 'warning', 'SMB probe latency is high.', 'probe', 'demo-provisioning-cancelled', NULL, 'demo-health-endpoint-lyon', UTC_TIMESTAMP() - INTERVAL 35 MINUTE, JSON_OBJECT('latency_ms', 1250)),
  ('storage_root', @root_finance_id, 'acl_alignment', 'success', 'info', 'Discovered ACLs match governed groups.', 'reconciliation', 'demo-provisioning-succeeded', @job_succeeded_id, 'demo-health-root-finance', UTC_TIMESTAMP() - INTERVAL 4 MINUTE, JSON_OBJECT('groups_checked', 2)),
  ('storage_root', @root_hr_id, 'provisioning', 'failed', 'critical', 'WRITE group provisioning failed.', 'provisioning_job', 'demo-provisioning-failed', @job_failed_id, 'demo-health-root-hr', UTC_TIMESTAMP() - INTERVAL 25 MINUTE, JSON_OBJECT('error_code', 'AD_GROUP_CREATE_FAILED')),
  ('identity_source', @demo_ad_source_id, 'snapshot', 'success', 'info', 'Active demo directory snapshot loaded.', 'snapshot', 'demo-directory-snapshot-active', NULL, 'demo-health-identity-source', UTC_TIMESTAMP() - INTERVAL 10 MINUTE, JSON_OBJECT('snapshot_version', 7)),
  ('storage_endpoint', @endpoint_marseille_id, 'probe', 'success', 'info', 'NFS probe succeeded.', 'probe', 'demo-provisioning-succeeded-shared', @job_succeeded_shared_id, 'demo-health-endpoint-marseille', UTC_TIMESTAMP() - INTERVAL 8 MINUTE, JSON_OBJECT('latency_ms', 42)),
  ('storage_root', @root_engineering_id, 'acl_alignment', 'success', 'info', 'Engineering governed groups match expected inventory.', 'reconciliation', 'demo-provisioning-succeeded-shared', @job_succeeded_shared_id, 'demo-health-root-engineering', UTC_TIMESTAMP() - INTERVAL 8 MINUTE, JSON_OBJECT('groups_checked', 2)),
  ('storage_root', @root_shared_id, 'provisioning', 'warning', 'warning', 'Shared write provisioning is retrying.', 'provisioning_job', 'demo-provisioning-retrying-shared-write', @job_retrying_shared_write_id, 'demo-health-root-shared', UTC_TIMESTAMP() - INTERVAL 5 MINUTE, JSON_OBJECT('retry_count', 2)),
  ('storage_endpoint', @endpoint_nantes_id, 'probe', 'running', 'warning', 'Legal endpoint probe still running.', 'probe', 'demo-provisioning-running-legal', @job_running_legal_id, 'demo-health-endpoint-nantes', UTC_TIMESTAMP() - INTERVAL 2 MINUTE, JSON_OBJECT('progress', 65)),
  ('storage_root', @root_lab_id, 'provisioning', 'unknown', 'warning', 'Lab Sandbox group provisioning has not started.', 'provisioning_job', 'demo-provisioning-queued-lab', @job_queued_lab_id, 'demo-health-root-lab', UTC_TIMESTAMP() - INTERVAL 20 MINUTE, JSON_OBJECT('expected_group', 'B2S_LAB_READ'));

COMMIT;
