-- ============================================================
-- BornToShare Wizard - Logging DB views pack
-- ============================================================

DROP VIEW IF EXISTS v_audit_journey;
DROP VIEW IF EXISTS v_audit_by_action;
DROP VIEW IF EXISTS v_audit_by_actor;
DROP VIEW IF EXISTS v_audit_by_service;

CREATE OR REPLACE VIEW v_audit_by_action AS
SELECT
  action,
  result,
  severity,
  COUNT(*) AS events_count,
  MAX(event_time) AS last_event_time
FROM audit_event
GROUP BY action, result, severity;

CREATE OR REPLACE VIEW v_audit_by_actor AS
SELECT
  actor_type,
  actor_id,
  COUNT(*) AS events_count,
  MAX(event_time) AS last_event_time
FROM audit_event
GROUP BY actor_type, actor_id;

CREATE OR REPLACE VIEW v_audit_by_service AS
SELECT
  source_service,
  COUNT(*) AS events_count,
  MAX(event_time) AS last_event_time
FROM audit_event
GROUP BY source_service;

CREATE OR REPLACE VIEW v_audit_journey AS
SELECT
  LOWER(HEX(id)) AS id,
  event_time,
  actor_type,
  actor_id,
  action,
  entity_type,
  entity_id,
  zone_id,
  root_id,
  endpoint_id,
  result,
  severity,
  correlation_id,
  source_service,
  metadata_json
FROM audit_event;
