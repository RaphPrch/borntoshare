-- Installations created before these rules: the creation files of the wizard already hold them.
-- Stops with a duplicate-key error if the data has duplicates: they must be merged first, no data is removed here.
-- Idempotent: can be applied again.

ALTER TABLE zones
  ADD UNIQUE KEY IF NOT EXISTS uq_zones_name (name),
  ADD UNIQUE KEY IF NOT EXISTS uq_zones_code (code);

ALTER TABLE identity_sources
  ADD UNIQUE KEY IF NOT EXISTS uq_identity_sources_name (name);

ALTER TABLE identities
  ADD UNIQUE KEY IF NOT EXISTS uq_identities_source_username (source_id, username);

UPDATE access_requests ar LEFT JOIN identities i ON i.id = ar.requester_identity_id
SET ar.requester_identity_id = NULL
WHERE ar.requester_identity_id IS NOT NULL AND i.id IS NULL;

ALTER TABLE access_requests
  ADD CONSTRAINT fk_access_requests_requester FOREIGN KEY IF NOT EXISTS (requester_identity_id) REFERENCES identities(id) ON DELETE SET NULL;

UPDATE provisioning_jobs j LEFT JOIN identity_sources s ON s.id = j.identity_source_id
SET j.identity_source_id = NULL
WHERE j.identity_source_id IS NOT NULL AND s.id IS NULL;

ALTER TABLE provisioning_jobs
  ADD CONSTRAINT fk_provisioning_jobs_identity_source FOREIGN KEY IF NOT EXISTS (identity_source_id) REFERENCES identity_sources(id) ON DELETE SET NULL;

-- Status of objects that no longer exist
DELETE c FROM infra_component_status c
LEFT JOIN identity_sources s ON c.component = CONCAT('identity_source:', s.id)
WHERE c.component LIKE 'identity_source:%' AND s.id IS NULL;

DELETE c FROM infra_component_status c
LEFT JOIN storage_endpoints e ON c.component = CONCAT('storage_endpoint:', e.id)
WHERE c.component LIKE 'storage_endpoint:%' AND e.id IS NULL;

-- Passwords of objects that no longer exist
DELETE si FROM secret_items si
WHERE NOT EXISTS (SELECT 1 FROM identity_sources s WHERE s.bind_password_ref = si.ref)
  AND NOT EXISTS (SELECT 1 FROM identity_source_service_accounts a WHERE a.bind_password_ref = si.ref)
  AND NOT EXISTS (SELECT 1 FROM storage_endpoints e WHERE e.bind_password_ref = si.ref)
  AND NOT EXISTS (SELECT 1 FROM sso_providers p WHERE p.client_secret_ref = si.ref)
  AND si.updated_at < NOW() - INTERVAL 1 DAY;
