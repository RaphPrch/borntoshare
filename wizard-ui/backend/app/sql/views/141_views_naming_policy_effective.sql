-- Effective naming policy read-models (V1 strict)

DROP VIEW IF EXISTS v_naming_policy_effective_zone;
CREATE OR REPLACE VIEW v_naming_policy_effective_zone AS
SELECT
  z.id AS zone_id,
  z.code AS zone_code,
  COALESCE(oz.override_enabled, 0) AS override_enabled,
  COALESCE(oz.group_prefix, g.group_prefix) AS group_prefix,
  COALESCE(oz.template, g.template) AS template,
  COALESCE(oz.normalize_uppercase, g.normalize_uppercase) AS normalize_uppercase,
  COALESCE(oz.max_sam_length, g.max_sam_length) AS max_sam_length,
  COALESCE(oz.replace_map_json, g.replace_map_json) AS replace_map_json,
  COALESCE(oz.rootcode_strategy, g.rootcode_strategy) AS rootcode_strategy,
  CASE
    WHEN oz.scope_id IS NOT NULL AND COALESCE(oz.override_enabled, 0) = 1 THEN 'zone'
    ELSE 'global'
  END AS resolved_from_scope,
  COALESCE(oz.updated_at, g.updated_at) AS updated_at
FROM zones z
JOIN naming_policy_global g ON g.id = 1
LEFT JOIN naming_policy_overrides oz
  ON oz.scope_type = 'zone'
 AND oz.scope_id = z.id;


DROP VIEW IF EXISTS v_naming_policy_effective_storage_endpoint;
CREATE OR REPLACE VIEW v_naming_policy_effective_storage_endpoint AS
SELECT
  se.id AS storage_endpoint_id,
  se.zone_id,
  npz.zone_code,
  COALESCE(oe.override_enabled, 0) AS override_enabled,
  COALESCE(oe.group_prefix, npz.group_prefix) AS group_prefix,
  COALESCE(oe.template, npz.template) AS template,
  COALESCE(oe.normalize_uppercase, npz.normalize_uppercase) AS normalize_uppercase,
  COALESCE(oe.max_sam_length, npz.max_sam_length) AS max_sam_length,
  COALESCE(oe.replace_map_json, npz.replace_map_json) AS replace_map_json,
  COALESCE(oe.rootcode_strategy, npz.rootcode_strategy) AS rootcode_strategy,
  CASE
    WHEN oe.scope_id IS NOT NULL AND COALESCE(oe.override_enabled, 0) = 1 THEN 'storage_endpoint'
    ELSE npz.resolved_from_scope
  END AS resolved_from_scope,
  COALESCE(oe.updated_at, npz.updated_at) AS updated_at
FROM storage_endpoints se
LEFT JOIN v_naming_policy_effective_zone npz ON npz.zone_id = se.zone_id
LEFT JOIN naming_policy_overrides oe
  ON oe.scope_type = 'storage_endpoint'
 AND oe.scope_id = se.id;


DROP VIEW IF EXISTS v_naming_policy_effective_storage_root;
CREATE OR REPLACE VIEW v_naming_policy_effective_storage_root AS
SELECT
  sr.id AS storage_root_id,
  sr.storage_endpoint_id,
  sr.parent_storage_root_id,
  npe.zone_id,
  npe.zone_code,
  COALESCE(oroot.override_enabled, 0) AS override_enabled,
  COALESCE(oroot.group_prefix, npe.group_prefix) AS group_prefix,
  COALESCE(oroot.template, npe.template) AS template,
  COALESCE(oroot.normalize_uppercase, npe.normalize_uppercase) AS normalize_uppercase,
  COALESCE(oroot.max_sam_length, npe.max_sam_length) AS max_sam_length,
  COALESCE(oroot.replace_map_json, npe.replace_map_json) AS replace_map_json,
  COALESCE(oroot.rootcode_strategy, npe.rootcode_strategy) AS rootcode_strategy,
  CASE
    WHEN oroot.scope_id IS NOT NULL AND COALESCE(oroot.override_enabled, 0) = 1 THEN 'storage_root'
    ELSE npe.resolved_from_scope
  END AS resolved_from_scope,
  COALESCE(oroot.updated_at, npe.updated_at) AS updated_at
FROM storage_roots sr
JOIN v_naming_policy_effective_storage_endpoint npe ON npe.storage_endpoint_id = sr.storage_endpoint_id
LEFT JOIN naming_policy_overrides oroot
  ON oroot.scope_type = 'storage_root'
 AND oroot.scope_id = sr.id;
