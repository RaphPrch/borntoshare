from __future__ import annotations

import json
import uuid
import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.logging_db import LoggingSessionLocal


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")


def _compute_hash(prev_hash: str | None, event_payload: dict[str, Any]) -> tuple[str | None, str]:
    prev = (prev_hash or "").strip() or None
    material = {
        "prev": prev,
        "event": event_payload,
    }
    cur = _sha256_hex(_canonical_json(material))
    return prev, cur


def _is_retryable_mysql_lock_error(exc: Exception) -> bool:
    """MySQL deadlock / lock-timeout detection (PyMySQL wrapped by SQLAlchemy)."""
    if not isinstance(exc, OperationalError):
        return False

    # SQLAlchemy wraps DBAPI error in .orig, usually (errno, message)
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ()) if orig is not None else ()

    errno = None
    if args:
        try:
            errno = int(args[0])
        except Exception:
            errno = None

    # 1213 = deadlock, 1205 = lock wait timeout exceeded
    return errno in {1213, 1205}


def _row_to_activity(r: dict[str, Any]) -> dict[str, Any]:
    meta = r.get("metadata_json") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    def _to_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _normalize_value(value: Any) -> str:
        if value is None:
            return "∅"
        if isinstance(value, (str, int, float, bool)):
            text = str(value).strip()
            return text if text else "∅"
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(value)

    ctx = _to_dict(meta.get("context_json"))
    details_blob = _to_dict(meta.get("details"))
    before = _to_dict(meta.get("before") or ctx.get("before") or details_blob.get("before"))
    after = _to_dict(meta.get("after") or ctx.get("after") or details_blob.get("after"))

    details_changes: list[dict[str, str]] = []
    if before or after:
        keys = sorted(set(before.keys()) | set(after.keys()))
        for key in keys:
            prev = before.get(key)
            nxt = after.get(key)
            if prev == nxt:
                continue
            details_changes.append(
                {
                    "field": str(key),
                    "from": _normalize_value(prev),
                    "to": _normalize_value(nxt),
                }
            )

    action = str(r.get("action") or "").strip()
    entity_type = r.get("entity_type")

    target_display = (
        meta.get("target_display")
        or meta.get("zone_name")
        or meta.get("endpoint")
        or meta.get("root")
        or meta.get("request_code")
        or meta.get("job_id")
    )

    module = str(r.get("source_service") or "unknown").strip() or "unknown"
    category = str(action.split(".", 1)[0] if "." in action else "system").strip() or "system"

    activity: dict[str, Any] = {
        "id": r.get("id"),
        "actor_type": r.get("actor_type"),
        "actor_id": r.get("actor_id"),
        "actor_display": meta.get("actor_display"),
        "action": action,
        "outcome": r.get("result"),
        "target_type": entity_type,
        "target_id": r.get("entity_id"),
        "target_display": target_display,
        "context_json": meta.get("context_json") if meta.get("context_json") is not None else meta,
        "details_changes": details_changes,
        "correlation_id": r.get("correlation_id"),
        "created_at": r.get("event_time"),
        # Helpful extra fields for future UI
        "severity": r.get("severity"),
        "source_service": module,
        "module": module,
        "category": category,
        "zone_id": r.get("zone_id"),
        "root_id": r.get("root_id"),
        "endpoint_id": r.get("endpoint_id"),
    }

    activity["is_business"] = _is_business_activity(activity)
    return activity


def _is_business_activity(activity: dict[str, Any]) -> bool:
    action = str(activity.get("action") or "").strip().lower()
    actor_type = str(activity.get("actor_type") or "").strip().lower()
    target_type = str(activity.get("target_type") or "").strip().lower()

    noisy_exact = {
        "dashboard.refreshed",
        "activity_list_latest",
        "activity_list_by_target",
        "activity_list_by_actor",
        "activity_create",
        "seed.started",
    }
    if action in noisy_exact:
        return False

    noisy_prefixes = (
        "http.",
        "api.",
        "request.",
        "response.",
        "ui.",
        "frontend.",
        "frontend.http",
    )
    if any(action.startswith(p) for p in noisy_prefixes):
        return False

    business_target_types = {
        "zone",
        "storage_endpoint",
        "storage_root",
        "access_request",
        "access_request_item_execution",
        "storage_root_access_profile",
        "naming_policy_overrides",
        "capsule_execution",
        "group_membership_snapshot",
        "identity_group",
        "acl",
    }
    if target_type in business_target_types:
        return True

    business_action_prefixes = (
        "zone.",
        "storage_endpoint.",
        "storage_root.",
        "access_request.",
        "provisioning_job.",
        "acl.",
        "group.",
        "ad_group.",
        "naming_policy.",
        "policy.",
        "identity_orchestration.",
        "capsule_execution.",
    )
    if any(action.startswith(p) for p in business_action_prefixes):
        return True

    return actor_type in {"user", "system"}


def list_latest(*, limit: int = 100, business_only: bool = False) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 100), 500))
    query_limit = min(500, max(limit * 5, limit)) if business_only else limit
    with LoggingSessionLocal() as db:
        rows = db.execute(
            text(
                """
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
                FROM audit_event
                ORDER BY event_time DESC
                LIMIT :limit
                """
            ),
            {"limit": query_limit},
        ).mappings().all()
        activities = [_row_to_activity(dict(r)) for r in rows]
        if business_only:
            activities = [a for a in activities if bool(a.get("is_business"))]
        return activities[:limit]


def list_by_target(*, target_type: str, target_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 200), 500))
    target_type = str(target_type or "").strip()
    if not target_type:
        return []

    with LoggingSessionLocal() as db:
        if target_id is None:
            rows = db.execute(
                text(
                    """
                    SELECT
                      LOWER(HEX(id)) AS id,
                      event_time, actor_type, actor_id, action,
                      entity_type, entity_id,
                      zone_id, root_id, endpoint_id,
                      result, severity,
                      correlation_id, source_service, metadata_json
                    FROM audit_event
                    WHERE entity_type = :etype
                    ORDER BY event_time DESC
                    LIMIT :limit
                    """
                ),
                {"etype": target_type, "limit": limit},
            ).mappings().all()
        else:
            rows = db.execute(
                text(
                    """
                    SELECT
                      LOWER(HEX(id)) AS id,
                      event_time, actor_type, actor_id, action,
                      entity_type, entity_id,
                      zone_id, root_id, endpoint_id,
                      result, severity,
                      correlation_id, source_service, metadata_json
                    FROM audit_event
                    WHERE entity_type = :etype AND entity_id = :eid
                    ORDER BY event_time DESC
                    LIMIT :limit
                    """
                ),
                {"etype": target_type, "eid": str(target_id), "limit": limit},
            ).mappings().all()

        return [_row_to_activity(dict(r)) for r in rows]


def create_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Append-only insert into audit_event.

    Expected payload keys (best-effort):
    - action, actor_type, actor_id, actor_display
    - target_type/entity_type, target_id/entity_id, target_display
    - zone_id, root_id, endpoint_id
    - outcome/result, severity
    - correlation_id, source_service
    - context_json / metadata_json
    """
    if not isinstance(payload, dict):
        payload = {}

    action = str(payload.get("action") or "").strip() or "unknown_action"
    actor_type = str(payload.get("actor_type") or "system").strip().lower() or "system"
    actor_id = payload.get("actor_id")
    actor_id = None if actor_id is None else str(actor_id)

    entity_type = str(payload.get("entity_type") or payload.get("target_type") or "").strip() or None
    entity_id = payload.get("entity_id") or payload.get("target_id")
    entity_id = None if entity_id is None else str(entity_id)

    zone_id = payload.get("zone_id")
    zone_id = None if zone_id is None else str(zone_id)
    root_id = payload.get("root_id") or payload.get("storage_root_id")
    root_id = None if root_id is None else str(root_id)
    endpoint_id = payload.get("endpoint_id")
    endpoint_id = None if endpoint_id is None else str(endpoint_id)

    result = str(payload.get("result") or payload.get("outcome") or "success").strip().lower()
    if result not in {"success", "failure", "denied"}:
        result = "success"

    severity = str(payload.get("severity") or "info").strip().lower()
    if severity not in {"info", "warning", "high", "critical"}:
        severity = "info"

    correlation_id = str(payload.get("correlation_id") or "").strip() or uuid.uuid4().hex[:16]
    source_service = str(payload.get("source_service") or payload.get("source") or "unknown").strip() or "unknown"

    # Merge metadata
    meta: dict[str, Any] = {}
    for k in ("metadata_json", "context_json"):
        v = payload.get(k)
        if isinstance(v, dict):
            meta.update(v)
    # enrich with display fields if present
    if payload.get("actor_display") is not None:
        meta["actor_display"] = payload.get("actor_display")
    if payload.get("target_display") is not None:
        meta["target_display"] = payload.get("target_display")
    if payload.get("context_json") is not None:
        meta["context_json"] = payload.get("context_json")

    event_time = _utc_now()

    # Prepare canonical event payload (for hash chain)
    canonical = {
        "event_time": event_time.isoformat(timespec="microseconds"),
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "zone_id": zone_id,
        "root_id": root_id,
        "endpoint_id": endpoint_id,
        "result": result,
        "severity": severity,
        "correlation_id": correlation_id,
        "source_service": source_service,
        "metadata_json": meta,
    }

    new_id = uuid.uuid4()
    new_id_bytes = new_id.bytes

    # Retry short transactions on deadlock/lock-timeout to avoid noisy WARN logs
    # under concurrent writers while preserving hash-chain consistency.
    max_attempts = 5
    base_backoff_s = 0.05

    last_lock_exc: OperationalError | None = None
    hash_current: str | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            with LoggingSessionLocal() as db:
                # Concurrency: lock last row hash for consistent chain
                last = db.execute(
                    text("""SELECT hash_current FROM audit_event ORDER BY event_time DESC LIMIT 1 FOR UPDATE""")
                ).mappings().first()
                prev_hash = None if not last else last.get("hash_current")

                hash_prev, hash_current = _compute_hash(prev_hash, canonical)

                db.execute(
                    text(
                        """
                        INSERT INTO audit_event (
                          id, event_time,
                          actor_type, actor_id,
                          action, entity_type, entity_id,
                          zone_id, root_id, endpoint_id,
                          result, severity,
                          correlation_id, source_service,
                          metadata_json,
                          hash_prev, hash_current
                        )
                        VALUES (
                          :id, :event_time,
                          :actor_type, :actor_id,
                          :action, :entity_type, :entity_id,
                          :zone_id, :root_id, :endpoint_id,
                          :result, :severity,
                          :correlation_id, :source_service,
                          :metadata_json,
                          :hash_prev, :hash_current
                        )
                        """
                    ),
                    {
                        "id": new_id_bytes,
                        "event_time": event_time,
                        "actor_type": actor_type,
                        "actor_id": actor_id,
                        "action": action,
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "zone_id": zone_id,
                        "root_id": root_id,
                        "endpoint_id": endpoint_id,
                        "result": result,
                        "severity": severity,
                        "correlation_id": correlation_id,
                        "source_service": source_service,
                        "metadata_json": json.dumps(meta, ensure_ascii=False),
                        "hash_prev": hash_prev,
                        "hash_current": hash_current,
                    },
                )
                db.commit()
                break
        except OperationalError as exc:
            if not _is_retryable_mysql_lock_error(exc):
                raise

            last_lock_exc = exc
            if attempt >= max_attempts:
                raise

            time.sleep(base_backoff_s * attempt)

    if hash_current is None and last_lock_exc is not None:
        raise last_lock_exc

    return {
        "ok": True,
        "id": new_id.hex,
        "hash_current": hash_current,
    }
