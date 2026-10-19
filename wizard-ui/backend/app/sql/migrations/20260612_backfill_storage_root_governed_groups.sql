-- BornToShare
-- Additive backfill for the future governed-groups source of truth.
--
-- Scope:
-- - inserts missing storage_root_governed_groups rows from legacy
--   storage_root_access_profiles
-- - idempotent: safe to re-run
-- - no updates to legacy tables
-- - no deletes

INSERT INTO storage_root_governed_groups (
  storage_root_id,
  identity_source_id,
  permission_level,
  group_dn,
  group_sid,
  group_sam_account_name,
  group_display_name,
  managed_by,
  provisioning_status,
  is_active,
  created_from,
  metadata_json,
  last_verified_at
)
SELECT
  srap.storage_root_id,
  se.identity_source_id,
  level.permission_level,
  CASE
    WHEN srap.group_name LIKE '%=%' AND srap.group_name LIKE '%,%' THEN srap.group_name
    ELSE NULL
  END AS group_dn,
  CASE
    WHEN UPPER(COALESCE(srap.group_external_id, '')) LIKE 'S-%' THEN srap.group_external_id
    ELSE NULL
  END AS group_sid,
  CASE
    WHEN srap.group_name LIKE '%=%' AND srap.group_name LIKE '%,%' THEN NULL
    ELSE srap.group_name
  END AS group_sam_account_name,
  COALESCE(NULLIF(srap.name, ''), NULLIF(ap.name, '')) AS group_display_name,
  CASE
    WHEN UPPER(COALESCE(srap.source, '')) = 'EXTERNAL' THEN 'external'
    ELSE 'borntoshare'
  END AS managed_by,
  CASE
    WHEN UPPER(COALESCE(srap.source, '')) = 'EXTERNAL' THEN 'unmanaged'
    WHEN UPPER(COALESCE(srap.status, '')) IN ('SUCCEEDED', 'SUCCESS', 'DONE', 'OK') THEN 'provisioned'
    WHEN UPPER(COALESCE(srap.status, '')) IN ('FAILED', 'ERROR') THEN 'failed'
    ELSE 'pending'
  END AS provisioning_status,
  1 AS is_active,
  'migrated_access_profile' AS created_from,
  JSON_OBJECT(
    'legacy_storage_root_access_profile_id', srap.id,
    'legacy_access_profile_id', srap.access_profile_id,
    'legacy_status', srap.status,
    'legacy_group_external_id', srap.group_external_id,
    'legacy_source', srap.source,
    'migration_source', 'storage_root_access_profiles'
  ) AS metadata_json,
  COALESCE(srap.updated_at, srap.created_at) AS last_verified_at
FROM storage_root_access_profiles srap
JOIN storage_roots sr ON sr.id = srap.storage_root_id
JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
LEFT JOIN access_profiles ap ON ap.id = srap.access_profile_id
JOIN (
  SELECT
    inner_srap.id,
    CASE
      WHEN UPPER(
        COALESCE(
          NULLIF(inner_srap.access_level_code, ''),
          NULLIF(inner_ap.code, ''),
          NULLIF(inner_ap.permission, ''),
          ''
        )
      ) = 'WRITE' THEN 'WRITE'
      WHEN UPPER(
        COALESCE(
          NULLIF(inner_srap.access_level_code, ''),
          NULLIF(inner_ap.code, ''),
          NULLIF(inner_ap.permission, ''),
          ''
        )
      ) = 'READ' THEN 'READ'
      ELSE NULL
    END AS permission_level
  FROM storage_root_access_profiles inner_srap
  LEFT JOIN access_profiles inner_ap ON inner_ap.id = inner_srap.access_profile_id
) AS level ON level.id = srap.id
WHERE COALESCE(srap.active, 1) = 1
  AND srap.deleted_at IS NULL
  AND level.permission_level IS NOT NULL
  AND COALESCE(NULLIF(srap.group_name, ''), NULLIF(srap.group_external_id, '')) IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM storage_root_governed_groups srg
    WHERE srg.storage_root_id = srap.storage_root_id
      AND UPPER(COALESCE(srg.permission_level, '')) = level.permission_level
      AND COALESCE(NULLIF(srg.group_sam_account_name, ''), NULLIF(srg.group_sid, ''), NULLIF(srg.group_dn, '')) =
          COALESCE(
            CASE
              WHEN srap.group_name LIKE '%=%' AND srap.group_name LIKE '%,%' THEN NULL
              ELSE NULLIF(srap.group_name, '')
            END,
            CASE
              WHEN UPPER(COALESCE(srap.group_external_id, '')) LIKE 'S-%' THEN NULLIF(srap.group_external_id, '')
              ELSE NULL
            END,
            CASE
              WHEN srap.group_name LIKE '%=%' AND srap.group_name LIKE '%,%' THEN NULLIF(srap.group_name, '')
              ELSE NULL
            END
          )
  );
