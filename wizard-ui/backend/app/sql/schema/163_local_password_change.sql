-- A local account whose password was set by someone else (the first administrator, created by the installation
-- wizard) changes it at its first sign-in: nothing else opens until then. Idempotent: can be applied again.

ALTER TABLE local_credentials ADD COLUMN IF NOT EXISTS must_change_password TINYINT(1) NOT NULL DEFAULT 0;
