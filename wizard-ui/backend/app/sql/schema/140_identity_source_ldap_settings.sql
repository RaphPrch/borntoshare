-- LDAPS check and user filter of each directory, set in the application (they were global, in .env).
-- tls_server_name: name in the certificate when the host of the source is an IP address.
-- Idempotent: can be applied again.

ALTER TABLE identity_sources
  ADD COLUMN IF NOT EXISTS tls_verify TINYINT(1) NOT NULL DEFAULT 1 AFTER bind_password_ref,
  ADD COLUMN IF NOT EXISTS tls_ca_pem TEXT NULL AFTER tls_verify,
  ADD COLUMN IF NOT EXISTS tls_server_name VARCHAR(255) NULL AFTER tls_ca_pem,
  ADD COLUMN IF NOT EXISTS user_filter VARCHAR(512) NULL AFTER tls_server_name;
