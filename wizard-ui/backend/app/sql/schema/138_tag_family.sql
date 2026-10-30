-- Family of a tag (Tags page): groups the catalogue, free text, none by default.
-- Idempotent: can be applied again.

ALTER TABLE tags ADD COLUMN IF NOT EXISTS family VARCHAR(100) NULL AFTER color;
