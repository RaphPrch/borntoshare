-- views/143_views_zone_provisioning_policy.sql
-- Effective zone provisioning policy preview

CREATE OR REPLACE VIEW v_zone_provisioning_policy AS
SELECT
  z.id AS zone_id,
  COALESCE(zpp.enabled, 0) AS enabled,
  COALESCE(NULLIF(zpp.ou_strategy, ''), 'identity_default') AS ou_strategy,
  zpp.base_ou_dn AS base_ou_dn,
  zpp.static_ou_dn AS static_ou_dn,
  npez.template AS naming_template
FROM zones z
LEFT JOIN zone_provisioning_policy zpp ON zpp.zone_id = z.id
LEFT JOIN v_naming_policy_effective_zone npez ON npez.zone_id = z.id;
