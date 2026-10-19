-- ============================================================
-- BornToShare Wizard - Logging DB indexes pack
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_audit_event_time
  ON audit_event(event_time);

CREATE INDEX IF NOT EXISTS idx_audit_event_actor
  ON audit_event(actor_type, actor_id, event_time);

CREATE INDEX IF NOT EXISTS idx_audit_event_entity
  ON audit_event(entity_type, entity_id, event_time);

CREATE INDEX IF NOT EXISTS idx_audit_event_zone
  ON audit_event(zone_id, event_time);

CREATE INDEX IF NOT EXISTS idx_audit_event_root
  ON audit_event(root_id, event_time);

CREATE INDEX IF NOT EXISTS idx_audit_event_endpoint
  ON audit_event(endpoint_id, event_time);

CREATE INDEX IF NOT EXISTS idx_audit_event_action
  ON audit_event(action, event_time);

CREATE INDEX IF NOT EXISTS idx_audit_event_correlation
  ON audit_event(correlation_id);
