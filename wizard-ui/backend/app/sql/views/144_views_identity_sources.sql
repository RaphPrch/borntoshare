-- Identity sources read-model helpers

CREATE OR REPLACE VIEW v_identity_source_latest_snapshot AS
SELECT
  ids.id AS identity_source_id,
  latest.snapshot_id AS snapshot_id,
  latest.status AS last_snapshot_status,
  latest.snapshot_version AS last_snapshot_version,
  latest.last_snapshot_at AS last_snapshot_at,
  COALESCE(u.users_count, 0) AS last_snapshot_users_count,
  COALESCE(g.groups_count, 0) AS last_snapshot_groups_count,
  COALESCE(m.memberships_count, 0) AS last_snapshot_memberships_count,
  COALESCE(u.users_count, 0) + COALESCE(g.groups_count, 0) AS last_snapshot_objects_count
FROM identity_sources ids
LEFT JOIN (
  SELECT
    ranked.identity_source_id,
    ranked.id AS snapshot_id,
    ranked.status,
    ranked.version AS snapshot_version,
    ranked.last_snapshot_at
  FROM (
    SELECT
      ds.id,
      ds.identity_source_id,
      ds.status,
      ds.version,
      COALESCE(ds.activated_at, ds.completed_at, ds.finished_at, ds.started_at, ds.updated_at, ds.created_at) AS last_snapshot_at,
      ROW_NUMBER() OVER (
        PARTITION BY ds.identity_source_id
        ORDER BY COALESCE(ds.activated_at, ds.completed_at, ds.finished_at, ds.started_at, ds.updated_at, ds.created_at) DESC, ds.id DESC
      ) AS rn
    FROM directory_snapshots ds
    WHERE ds.status IN ('ACTIVE', 'SUCCEEDED')
  ) ranked
  WHERE ranked.rn = 1
) latest ON latest.identity_source_id = ids.id
LEFT JOIN (
  SELECT snapshot_id, COUNT(*) AS users_count
  FROM directory_snapshot_users
  GROUP BY snapshot_id
) u ON u.snapshot_id = latest.snapshot_id
LEFT JOIN (
  SELECT snapshot_id, COUNT(*) AS groups_count
  FROM directory_snapshot_groups
  GROUP BY snapshot_id
) g ON g.snapshot_id = latest.snapshot_id
LEFT JOIN (
  SELECT snapshot_id, COUNT(*) AS memberships_count
  FROM directory_snapshot_memberships
  GROUP BY snapshot_id
) m ON m.snapshot_id = latest.snapshot_id;
