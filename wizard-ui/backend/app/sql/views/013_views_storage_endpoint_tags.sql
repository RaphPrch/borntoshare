-- ============================================================
-- BornToShare — Views: Storage Endpoint Tags
-- EXTENDS CONTEXT (SAFE)
-- NO FUNCTIONAL LOSS / NO COLLISION
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ============================================================
-- Storage endpoint tags (FLAT)
-- ============================================================
DROP VIEW IF EXISTS v_storage_endpoint_tags;
CREATE OR REPLACE VIEW v_storage_endpoint_tags AS
SELECT
  se.id AS storage_endpoint_id,
  t.id AS tag_id,
  t.name AS tag_label,
  t.name AS tag_code,
  t.color AS tag_color
FROM storage_endpoints se
JOIN storage_roots sr ON sr.storage_endpoint_id = se.id
JOIN storage_root_tags srt ON srt.storage_root_id = sr.id
JOIN tags t ON t.id = srt.tag_id
WHERE srt.deleted_at IS NULL
GROUP BY se.id, t.id, t.name;
