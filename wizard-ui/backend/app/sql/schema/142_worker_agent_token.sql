-- The agent of a worker recognizes core-service with a proof derived from INTERNAL_TOKEN: no account to store any more.
-- Idempotent: can be applied again.

ALTER TABLE infra_workers
  DROP COLUMN IF EXISTS username,
  DROP COLUMN IF EXISTS password_ref;

DELETE FROM secret_items WHERE ref LIKE 'sm://infrastructure-worker/%';
