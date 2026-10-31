-- Kind of directory behind an LDAP source: its attributes and object classes differ (ad | openldap).
-- Idempotent: can be applied again.

ALTER TABLE identity_sources
  ADD COLUMN IF NOT EXISTS directory_flavor VARCHAR(16) NOT NULL DEFAULT 'ad' AFTER type;
