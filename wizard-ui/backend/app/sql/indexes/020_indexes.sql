-- ============================================================
-- BornToShare (B2S) — Indexes (CLEAN / SAFE)
-- MariaDB / MySQL (InnoDB, utf8mb4)
-- Secondary indexes only.
-- PK / UNIQUE / FK constraints stay in schema/*.sql.
-- ============================================================

-- ============================================================
-- identities
-- ============================================================
DROP INDEX IF EXISTS idx_identity_active ON identities;
DROP INDEX IF EXISTS idx_identity_email ON identities;
DROP INDEX IF EXISTS idx_identity_auth_source ON identities;
DROP INDEX IF EXISTS idx_identities_external_id ON identities;
DROP INDEX IF EXISTS idx_identities_type ON identities;

CREATE INDEX idx_identity_active ON identities(is_active);
CREATE INDEX idx_identity_email ON identities(email);
CREATE INDEX idx_identity_auth_source ON identities(auth_source);
CREATE INDEX idx_identities_external_id ON identities(external_id);
CREATE INDEX idx_identities_type ON identities(type);

-- ============================================================
-- identity_sources
-- ============================================================
DROP INDEX IF EXISTS idx_identity_sources_active ON identity_sources;
DROP INDEX IF EXISTS idx_identity_sources_type ON identity_sources;
DROP INDEX IF EXISTS idx_identity_sources_bind_password_ref ON identity_sources;
DROP INDEX IF EXISTS idx_identity_sources_auth_route ON identity_sources;
DROP INDEX IF EXISTS idx_identity_sources_external_id ON identity_sources;

CREATE INDEX idx_identity_sources_active ON identity_sources(is_active);
CREATE INDEX idx_identity_sources_type ON identity_sources(type);
CREATE INDEX idx_identity_sources_bind_password_ref
  ON identity_sources(bind_password_ref(190));
CREATE INDEX idx_identity_sources_auth_route
  ON identity_sources(type, is_active, auth_enabled, auth_priority, id);
CREATE INDEX idx_identity_sources_external_id ON identity_sources(external_id);

-- ============================================================
-- zones
-- ============================================================
DROP INDEX IF EXISTS idx_zone_active ON zones;
-- zones has no is_active column in V1

-- ============================================================
-- storage_endpoints
-- ============================================================
DROP INDEX IF EXISTS idx_storage_endpoint_active ON storage_endpoints;
DROP INDEX IF EXISTS idx_storage_endpoint_type ON storage_endpoints;

-- FK fk_storage_endpoints_zone_id requires an index on zone_id
-- Avoid dropping/recreating to prevent FK constraint errors
CREATE INDEX idx_storage_endpoint_type ON storage_endpoints(endpoint_type);
CREATE INDEX IF NOT EXISTS idx_storage_endpoints_zone
  ON storage_endpoints(zone_id);

-- ============================================================
-- storage_roots
-- ============================================================
DROP INDEX IF EXISTS idx_storage_root_active ON storage_roots;

-- FK fk_storage_roots_storage_endpoint_id requires an index on storage_endpoint_id
-- Avoid dropping/recreating to prevent FK constraint errors
CREATE INDEX IF NOT EXISTS idx_storage_roots_parent
  ON storage_roots(parent_storage_root_id);
CREATE INDEX IF NOT EXISTS idx_storage_roots_endpoint
  ON storage_roots(storage_endpoint_id);

-- ============================================================
-- access_profiles
-- NOTE: uq_access_profile_code already exists → no extra index
-- ============================================================
DROP INDEX IF EXISTS idx_ap_active ON access_profiles;

CREATE INDEX idx_ap_active ON access_profiles(active);

-- ============================================================
-- storage_root_access_profiles
-- ============================================================
-- FK fk_srap_access_profile_id requires an index on access_profile_id.
-- Do not drop idx_srap_access_profile: dropping can fail with 1553 when bound to FK.
-- Add a dedicated composite index for query performance in an idempotent way.
CREATE INDEX IF NOT EXISTS idx_srap_access_profile_root
  ON storage_root_access_profiles(access_profile_id, storage_root_id);

-- ============================================================
-- storage_root_access_profiles (new model)
-- ============================================================
-- indexes provided in schema/116_storage_root_profile_groups.sql

-- ============================================================
-- access_requests (dashboard hot paths)
-- ============================================================
DROP INDEX IF EXISTS idx_ar_requester_status_created ON access_requests;
DROP INDEX IF EXISTS idx_ar_storage_status ON access_requests;
DROP INDEX IF EXISTS idx_ar_status_updated ON access_requests;
DROP INDEX IF EXISTS idx_ar_profile ON access_requests;
DROP INDEX IF EXISTS idx_ar_expires_status ON access_requests;
DROP INDEX IF EXISTS idx_ar_sla_status_created ON access_requests;

CREATE INDEX idx_ar_requester_status_created
  ON access_requests(requester_identity_id, status, created_at);

CREATE INDEX idx_ar_status_updated
  ON access_requests(status, updated_at);

-- ============================================================
-- Snapshot and directory lookup
-- ============================================================
DROP INDEX IF EXISTS idx_directory_users_identity_usn ON directory_users;
DROP INDEX IF EXISTS idx_directory_users_identity_when_changed ON directory_users;
DROP INDEX IF EXISTS idx_directory_group_members_user ON directory_group_members;
DROP INDEX IF EXISTS idx_directory_groups_identity_usn ON directory_groups;
DROP INDEX IF EXISTS idx_directory_groups_identity_when_changed ON directory_groups;
DROP INDEX IF EXISTS idx_directory_snapshots_source_status_created ON directory_snapshots;
DROP INDEX IF EXISTS idx_directory_snapshots_correlation_id ON directory_snapshots;
DROP INDEX IF EXISTS idx_directory_snapshot_users_lookup ON directory_snapshot_users;
DROP INDEX IF EXISTS idx_directory_snapshot_users_snapshot_source ON directory_snapshot_users;
DROP INDEX IF EXISTS idx_directory_snapshot_users_usn ON directory_snapshot_users;
DROP INDEX IF EXISTS idx_directory_snapshot_users_when_changed ON directory_snapshot_users;
DROP INDEX IF EXISTS idx_dsu_snapshot_active_dn ON directory_snapshot_users;
DROP INDEX IF EXISTS idx_dsu_snapshot_dn ON directory_snapshot_users;
DROP INDEX IF EXISTS idx_directory_snapshot_groups_lookup ON directory_snapshot_groups;
DROP INDEX IF EXISTS idx_directory_snapshot_groups_snapshot_source ON directory_snapshot_groups;
DROP INDEX IF EXISTS idx_directory_snapshot_groups_usn ON directory_snapshot_groups;
DROP INDEX IF EXISTS idx_directory_snapshot_groups_when_changed ON directory_snapshot_groups;
DROP INDEX IF EXISTS idx_dsg_snapshot_dn ON directory_snapshot_groups;
DROP INDEX IF EXISTS idx_directory_snapshot_memberships_group ON directory_snapshot_memberships;
DROP INDEX IF EXISTS idx_directory_snapshot_memberships_member ON directory_snapshot_memberships;
DROP INDEX IF EXISTS idx_directory_snapshot_memberships_snapshot_source ON directory_snapshot_memberships;
DROP INDEX IF EXISTS idx_du_source_dn ON directory_users;
DROP INDEX IF EXISTS idx_du_source_username ON directory_users;
DROP INDEX IF EXISTS idx_du_source_upn ON directory_users;
DROP INDEX IF EXISTS idx_du_source_email ON directory_users;
DROP INDEX IF EXISTS idx_dg_source_dn ON directory_groups;
DROP INDEX IF EXISTS idx_dg_source_name ON directory_groups;
DROP INDEX IF EXISTS idx_dg_source_code ON directory_groups;

CREATE INDEX idx_directory_users_identity_usn ON directory_users(identity_source_id, usn_changed);
CREATE INDEX idx_directory_users_identity_when_changed ON directory_users(identity_source_id, when_changed);
CREATE INDEX idx_directory_group_members_user ON directory_group_members(directory_user_id);
CREATE INDEX idx_directory_groups_identity_usn ON directory_groups(identity_source_id, usn_changed);
CREATE INDEX idx_directory_groups_identity_when_changed ON directory_groups(identity_source_id, when_changed);
CREATE INDEX idx_directory_snapshots_source_status_created
  ON directory_snapshots(identity_source_id, status, created_at);
CREATE INDEX idx_directory_snapshots_correlation_id
  ON directory_snapshots(correlation_id);
CREATE INDEX idx_directory_snapshot_users_lookup
  ON directory_snapshot_users(snapshot_id, username, upn, email);
CREATE INDEX idx_directory_snapshot_users_snapshot_source
  ON directory_snapshot_users(snapshot_id, identity_source_id);
CREATE INDEX idx_directory_snapshot_users_usn
  ON directory_snapshot_users(snapshot_id, usn_changed);
CREATE INDEX idx_directory_snapshot_users_when_changed
  ON directory_snapshot_users(snapshot_id, when_changed);
CREATE INDEX idx_dsu_snapshot_active_dn
  ON directory_snapshot_users(snapshot_id, is_active, dn(190));
CREATE INDEX idx_dsu_snapshot_dn
  ON directory_snapshot_users(snapshot_id, dn(190));
CREATE INDEX idx_directory_snapshot_groups_lookup
  ON directory_snapshot_groups(snapshot_id, name, code);
CREATE INDEX idx_directory_snapshot_groups_snapshot_source
  ON directory_snapshot_groups(snapshot_id, identity_source_id);
CREATE INDEX idx_directory_snapshot_groups_usn
  ON directory_snapshot_groups(snapshot_id, usn_changed);
CREATE INDEX idx_directory_snapshot_groups_when_changed
  ON directory_snapshot_groups(snapshot_id, when_changed);
CREATE INDEX idx_dsg_snapshot_dn
  ON directory_snapshot_groups(snapshot_id, dn(190));
CREATE INDEX idx_directory_snapshot_memberships_group
  ON directory_snapshot_memberships(snapshot_id, group_external_id, member_type);
CREATE INDEX idx_directory_snapshot_memberships_member
  ON directory_snapshot_memberships(snapshot_id, member_external_id, member_type);
CREATE INDEX idx_directory_snapshot_memberships_snapshot_source
  ON directory_snapshot_memberships(snapshot_id, identity_source_id);
CREATE INDEX idx_du_source_dn ON directory_users(identity_source_id, dn(190));
CREATE INDEX idx_du_source_username ON directory_users(identity_source_id, username);
CREATE INDEX idx_du_source_upn ON directory_users(identity_source_id, upn);
CREATE INDEX idx_du_source_email ON directory_users(identity_source_id, email);
CREATE INDEX idx_dg_source_dn ON directory_groups(identity_source_id, dn(190));
CREATE INDEX idx_dg_source_name ON directory_groups(identity_source_id, name);
CREATE INDEX idx_dg_source_code ON directory_groups(identity_source_id, code);

-- ============================================================
-- RBAC / workflow / governance
-- ============================================================
DROP INDEX IF EXISTS idx_identity_roles_identity_id ON identity_roles;
DROP INDEX IF EXISTS idx_identity_roles_directory_group_id ON identity_roles;
DROP INDEX IF EXISTS idx_identity_roles_role_id ON identity_roles;
DROP INDEX IF EXISTS idx_srr_root_role ON storage_root_roles;

CREATE INDEX idx_identity_roles_identity_id ON identity_roles(identity_id);
CREATE INDEX idx_identity_roles_directory_group_id ON identity_roles(directory_group_id);
CREATE INDEX idx_identity_roles_role_id ON identity_roles(role_id);
CREATE INDEX idx_srr_root_role ON storage_root_roles(root_id, role);

CREATE INDEX IF NOT EXISTS idx_arie_access_request_id_status
  ON access_request_item_executions(access_request_id, status);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON provisioning_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_root_status ON provisioning_jobs(storage_root_access_profile_id, status);
CREATE INDEX IF NOT EXISTS idx_provisioning_jobs_type_action ON provisioning_jobs(job_type, action);
CREATE INDEX IF NOT EXISTS idx_provisioning_status_created ON provisioning_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_governance_events_type_created ON governance_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_governance_events_target ON governance_events(target_type, target_id, created_at);
CREATE INDEX IF NOT EXISTS idx_governance_events_job_id ON governance_events(provisioning_job_id);
CREATE INDEX IF NOT EXISTS idx_governance_alerts_scope
  ON governance_alerts(scope_type, scope_id, status, severity);
CREATE INDEX IF NOT EXISTS idx_governance_alerts_root
  ON governance_alerts(storage_root_id, status, severity);
CREATE INDEX IF NOT EXISTS idx_governance_alerts_endpoint
  ON governance_alerts(storage_endpoint_id, status, severity);
CREATE INDEX IF NOT EXISTS idx_governance_alerts_type
  ON governance_alerts(alert_type, status);
CREATE INDEX IF NOT EXISTS idx_governance_alerts_last_seen
  ON governance_alerts(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_governance_health_events_entity_time
  ON governance_health_events(entity_type, entity_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_governance_health_events_status_time
  ON governance_health_events(status, severity, checked_at);
CREATE INDEX IF NOT EXISTS idx_governance_health_events_check_time
  ON governance_health_events(entity_type, check_type, checked_at);
CREATE INDEX IF NOT EXISTS idx_governance_health_events_job
  ON governance_health_events(job_id);
