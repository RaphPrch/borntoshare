DROP VIEW IF EXISTS v_identity_effective_roles;

CREATE OR REPLACE VIEW v_identity_effective_roles AS

-- 0b) Default role for any active identity (V1 baseline)
SELECT
  i.id AS identity_id,
  'user' AS role_code,
  'default' AS via
FROM identities i
WHERE i.is_active = 1

UNION ALL

-- 1) Direct grants (identity_id)
SELECT
  i.id     AS identity_id,
  r.code   AS role_code,
  'direct' AS via
FROM identities i
JOIN identity_roles ir ON ir.identity_id = i.id
JOIN roles r ON r.id = ir.role_id

UNION ALL

-- 2) Group grants (directory_group_id): member of the group, directly or through nested groups
--    (effective memberships of the last snapshot), for active sources that allow importing groups
SELECT
  i.id     AS identity_id,
  r.code   AS role_code,
  'group'  AS via
FROM identities i
JOIN identity_bindings ib ON ib.identity_id = i.id AND ib.deleted_at IS NULL
JOIN directory_effective_memberships dem ON dem.directory_user_id = ib.directory_user_id
JOIN identity_roles ir ON ir.directory_group_id = dem.directory_group_id
JOIN roles r ON r.id = ir.role_id
JOIN identity_sources s ON s.id = dem.identity_source_id
WHERE i.is_active = 1
  AND s.is_active = 1
  AND COALESCE(JSON_VALUE(s.capabilities, '$.import_groups'), 'true') NOT IN ('false', '0');
