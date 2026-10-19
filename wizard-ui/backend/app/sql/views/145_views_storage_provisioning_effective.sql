-- Storage provisioning effective read-model views

CREATE OR REPLACE VIEW v_storage_endpoint_provisioning_effective AS
SELECT
  se.id AS storage_endpoint_id,
  se.zone_id,
  se.endpoint_type,
  se.protocol,
  COALESCE(zpp.enabled, 0) AS enabled,
  COALESCE(NULLIF(zpp.policy_mode, ''), 'ON_FIRST_ACCESS_REQUEST') AS policy_mode,
  COALESCE(NULLIF(zpp.ou_strategy, ''), 'IDENTITY_DEFAULT') AS ou_strategy,
  ids.id AS effective_identity_source_id,
  ids.name AS effective_identity_source_name,
  UPPER(COALESCE(NULLIF(ids.type, ''), 'ad')) AS effective_identity_source_kind,
  ids.is_active AS effective_identity_source_is_active,
  ids.bind_password_ref AS effective_identity_source_bind_password_ref,
  ids.bind_dn AS effective_identity_source_bind_dn,
  ids.host AS effective_identity_source_host,
  ids.base_dn AS effective_identity_source_base_dn,
  ids.default_group_ou_dn AS default_group_ou_dn,
  COALESCE(
    NULLIF(se.sub_ou_dn, ''),
    NULLIF(zpp.base_ou_dn, ''),
    NULLIF(zpp.static_ou_dn, ''),
    NULLIF(ids.default_group_ou_dn, '')
  ) AS effective_ou_dn
FROM storage_endpoints se
LEFT JOIN zone_provisioning_policy zpp ON zpp.zone_id = se.zone_id
LEFT JOIN identity_sources ids ON ids.id = se.identity_source_id;


CREATE OR REPLACE VIEW v_storage_root_provisioning_effective AS
SELECT
  sr.id AS storage_root_id,
  sr.storage_endpoint_id,
  sr.parent_storage_root_id,
  sr.name AS storage_root_name,
  sr.root_path,
  sr.normalized_root_path,
  COALESCE(sr.inherit_access_profiles, 0) AS inherit_access_profiles,
  se.zone_id,
  se.endpoint_type,
  se.protocol,
  COALESCE(zpp.enabled, 0) AS enabled,
  COALESCE(NULLIF(zpp.policy_mode, ''), 'ON_FIRST_ACCESS_REQUEST') AS policy_mode,
  COALESCE(NULLIF(zpp.ou_strategy, ''), 'IDENTITY_DEFAULT') AS ou_strategy,
  ids.id AS effective_identity_source_id,
  ids.name AS effective_identity_source_name,
  UPPER(COALESCE(NULLIF(ids.type, ''), 'ad')) AS effective_identity_source_kind,
  ids.is_active AS effective_identity_source_is_active,
  ids.bind_password_ref AS effective_identity_source_bind_password_ref,
  ids.bind_dn AS effective_identity_source_bind_dn,
  ids.host AS effective_identity_source_host,
  ids.base_dn AS effective_identity_source_base_dn,
  ids.default_group_ou_dn AS default_group_ou_dn,
  COALESCE(
    NULLIF(se.sub_ou_dn, ''),
    NULLIF(zpp.base_ou_dn, ''),
    NULLIF(zpp.static_ou_dn, ''),
    NULLIF(ids.default_group_ou_dn, '')
  ) AS effective_ou_dn
FROM storage_roots sr
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
LEFT JOIN zone_provisioning_policy zpp ON zpp.zone_id = se.zone_id
LEFT JOIN identity_sources ids ON ids.id = se.identity_source_id;
