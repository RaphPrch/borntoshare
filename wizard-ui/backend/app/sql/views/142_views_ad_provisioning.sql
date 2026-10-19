-- AD provisioning read-model helpers (V1)

CREATE OR REPLACE VIEW v_storage_endpoints_identity_sources AS
SELECT
  se.id AS storage_endpoint_id,
  se.name AS storage_endpoint_name,
  se.zone_id,
  se.identity_source_id,
  ids.name AS identity_source_name,
  UPPER(COALESCE(NULLIF(ids.type, ''), 'ad')) AS identity_source_kind,
  ids.domain_name,
  ids.write_enabled,
  ids.base_dn,
  ids.default_group_ou_dn,
  ids.is_active AS identity_source_is_active
FROM storage_endpoints se
LEFT JOIN identity_sources ids ON ids.id = se.identity_source_id;


CREATE OR REPLACE VIEW v_storage_root_access_profiles_provisioning AS
SELECT
  srap.id,
  srap.storage_root_id,
  srap.access_profile_id,
  UPPER(COALESCE(NULLIF(srap.access_level_code, ''), NULLIF(ap.code, ''), NULLIF(ap.permission, ''), 'READ')) AS access_level_code,
  COALESCE(NULLIF(srap.status, ''), 'PENDING') AS status,
  srap.group_external_id AS group_external_id,
  SHA2(CONCAT(srap.storage_root_id, ':', UPPER(COALESCE(NULLIF(srap.access_level_code, ''), NULLIF(ap.code, ''), NULLIF(ap.permission, ''), 'READ')), ':', COALESCE(srap.group_external_id, srap.group_name, 'N/A')), 256) AS permission_hash,
  CAST(NULL AS CHAR(64)) AS error_code,
  srap.error_message,
  srap.created_at,
  srap.updated_at
FROM storage_root_access_profiles srap
LEFT JOIN access_profiles ap ON ap.id = srap.access_profile_id;
