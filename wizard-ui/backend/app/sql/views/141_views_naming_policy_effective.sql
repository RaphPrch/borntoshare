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
