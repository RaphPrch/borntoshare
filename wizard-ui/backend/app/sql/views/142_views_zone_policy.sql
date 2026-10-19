-- Effective zone provisioning policy
-- Always returns a row per zone (default values when no override row exists).

CREATE OR REPLACE VIEW v_zone_provisioning_policy_effective AS
SELECT
  z.id AS zone_id,
  COALESCE(p.enabled, 0) AS enabled,
  COALESCE(p.ou_strategy, 'IDENTITY_DEFAULT') AS ou_strategy,
  p.base_ou_dn AS base_ou_dn,
  p.static_ou_dn AS static_ou_dn,
  (
    SELECT
      CASE WHEN COUNT(DISTINCT se.identity_source_id) = 1
           THEN MAX(se.identity_source_id)
           ELSE NULL
      END
    FROM storage_endpoints se
    WHERE se.zone_id = z.id
      AND se.identity_source_id IS NOT NULL
  ) AS effective_identity_source_id,
  (
    SELECT ids.name
    FROM identity_sources ids
    WHERE ids.id = (
      SELECT
        CASE WHEN COUNT(DISTINCT se2.identity_source_id) = 1
             THEN MAX(se2.identity_source_id)
             ELSE NULL
        END
      FROM storage_endpoints se2
      WHERE se2.zone_id = z.id
        AND se2.identity_source_id IS NOT NULL
    )
    LIMIT 1
  ) AS effective_identity_source_name,
  CASE
    WHEN COALESCE(p.ou_strategy, 'IDENTITY_DEFAULT') = 'ZONE_STATIC'
      THEN COALESCE(NULLIF(p.static_ou_dn, ''), NULLIF(p.base_ou_dn, ''))
    ELSE COALESCE(
      NULLIF(p.base_ou_dn, ''),
      NULLIF(p.static_ou_dn, ''),
      (
        SELECT ids.default_group_ou_dn
        FROM identity_sources ids
        WHERE ids.id = (
          SELECT
            CASE WHEN COUNT(DISTINCT se3.identity_source_id) = 1
                 THEN MAX(se3.identity_source_id)
                 ELSE NULL
            END
          FROM storage_endpoints se3
          WHERE se3.zone_id = z.id
            AND se3.identity_source_id IS NOT NULL
        )
        LIMIT 1
      )
    )
  END AS effective_ou_dn,
  npez.template AS naming_template,
  COALESCE(p.updated_at, npez.updated_at) AS updated_at
FROM zones z
LEFT JOIN zone_provisioning_policy p
  ON p.zone_id = z.id
LEFT JOIN v_naming_policy_effective_zone npez
  ON npez.zone_id = z.id;
