-- ============================================================
-- BornToShare — every tag has a color (tags created without one showed no color)
-- Same palette as the API (DEFAULT_TAG_COLORS); idempotent.
-- ============================================================
UPDATE tags
SET color = ELT(1 + MOD(CONV(SUBSTRING(SHA1(LOWER(TRIM(name))), 1, 2), 16, 10), 8),
                '#2563eb', '#16a34a', '#9333ea', '#dc2626', '#0f766e', '#b45309', '#1d4ed8', '#6b7280')
WHERE color IS NULL OR TRIM(color) = '';
