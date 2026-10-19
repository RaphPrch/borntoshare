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

-- 2) Group grants (directory_group_id)
SELECT
  i.id     AS identity_id,
  r.code   AS role_code,
  'group'  AS via
FROM identities i
JOIN identity_bindings ib ON ib.identity_id = i.id
JOIN directory_group_members dgm ON dgm.directory_user_id = ib.directory_user_id
JOIN identity_roles ir ON ir.directory_group_id = dgm.group_id
JOIN roles r ON r.id = ir.role_id;
