from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


ENTITY_TYPES = {"identity_source", "storage_endpoint", "storage_root"}
STATUS_VALUES = {"success", "running", "warning", "failed", "unknown"}
SEVERITY_VALUES = {"info", "warning", "critical"}

STATUS_WEIGHT = {
    "failed": 50,
    "warning": 40,
    "running": 30,
    "unknown": 20,
    "success": 10,
}


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_entity_type(value: object) -> str:
    entity_type = str(value or "").strip().lower().replace("-", "_")
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unsupported health entity_type: {entity_type or '<empty>'}")
    return entity_type


def normalize_status(value: object, *, ok: bool | None = None) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    if raw in {"ok", "healthy", "reachable", "connected", "succeeded", "active"}:
        return "success"
    if raw in {"processing", "queued", "pending", "in_progress", "probing"}:
        return "running"
    if raw in {"error", "failure", "unreachable", "offline", "timeout", "timed_out"}:
        return "failed"
    if raw in {"degraded", "stale", "attention"}:
        return "warning"
    if raw in STATUS_VALUES:
        return raw
    if ok is True:
        return "success"
    if ok is False:
        return "failed"
    return "unknown"


def severity_for_status(status: str, severity: object | None = None) -> str:
    raw = str(severity or "").strip().lower()
    if raw in SEVERITY_VALUES:
        return raw
    if status == "failed":
        return "critical"
    if status in {"warning", "running"}:
        return "warning"
    return "info"


def record_health_event(
    db: Session,
    *,
    entity_type: str,
    entity_id: int | None,
    check_type: str,
    status: str,
    severity: str | None = None,
    message: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    job_id: int | None = None,
    correlation_id: str | None = None,
    checked_at: datetime | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    normalized_entity_type = normalize_entity_type(entity_type)
    numeric_entity_id = int(entity_id or 0)
    if numeric_entity_id <= 0:
        return

    normalized_status = normalize_status(status)
    normalized_severity = severity_for_status(normalized_status, severity)
    checked_at_value = checked_at or utcnow_naive()

    db.execute(
        text(
            """
            INSERT INTO governance_health_events (
              entity_type,
              entity_id,
              check_type,
              status,
              severity,
              message,
              source_type,
              source_id,
              job_id,
              correlation_id,
              checked_at,
              metadata_json
            )
            VALUES (
              :entity_type,
              :entity_id,
              :check_type,
              :status,
              :severity,
              :message,
              :source_type,
              :source_id,
              :job_id,
              :correlation_id,
              :checked_at,
              :metadata_json
            )
            """
        ),
        {
            "entity_type": normalized_entity_type,
            "entity_id": numeric_entity_id,
            "check_type": str(check_type or "health").strip().lower()[:64] or "health",
            "status": normalized_status,
            "severity": normalized_severity,
            "message": (str(message).strip()[:512] if message else None),
            "source_type": (str(source_type).strip()[:80] if source_type else None),
            "source_id": (str(source_id).strip()[:190] if source_id else None),
            "job_id": int(job_id) if job_id else None,
            "correlation_id": (str(correlation_id).strip()[:128] if correlation_id else None),
            "checked_at": checked_at_value,
            "metadata_json": json.dumps(metadata_json or {}, ensure_ascii=False),
        },
    )


def _coerce_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _json_value(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def list_health_events(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    limit: int = 100,
) -> list[dict[str, Any]]:
    normalized_entity_type = normalize_entity_type(entity_type)
    rows = db.execute(
        text(
            """
            SELECT
              id,
              entity_type,
              entity_id,
              check_type,
              status,
              severity,
              message,
              source_type,
              source_id,
              job_id,
              correlation_id,
              checked_at,
              metadata_json,
              created_at
            FROM governance_health_events
            WHERE entity_type = :entity_type
              AND entity_id = :entity_id
            ORDER BY checked_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {
            "entity_type": normalized_entity_type,
            "entity_id": int(entity_id),
            "limit": int(limit),
        },
    ).mappings().all()

    events: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        checked_at = _coerce_dt(item.get("checked_at"))
        created_at = _coerce_dt(item.get("created_at"))
        item["checked_at"] = checked_at.isoformat() if checked_at else None
        item["created_at"] = created_at.isoformat() if created_at else None
        item["metadata_json"] = _json_value(item.get("metadata_json"))
        events.append(item)
    return events


def summarize_health_history(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    days: int = 7,
) -> list[dict[str, Any]]:
    normalized_entity_type = normalize_entity_type(entity_type)
    bounded_days = min(max(int(days or 7), 1), 31)
    today = utcnow_naive().date()
    start_day = today - timedelta(days=bounded_days - 1)
    start_dt = datetime.combine(start_day, datetime.min.time())

    rows = db.execute(
        text(
            """
            SELECT
              id,
              check_type,
              status,
              severity,
              message,
              checked_at
            FROM governance_health_events
            WHERE entity_type = :entity_type
              AND entity_id = :entity_id
              AND checked_at >= :start_dt
            ORDER BY checked_at ASC, id ASC
            """
        ),
        {
            "entity_type": normalized_entity_type,
            "entity_id": int(entity_id),
            "start_dt": start_dt,
        },
    ).mappings().all()

    by_day: dict[date, list[dict[str, Any]]] = {}
    for row in rows:
        checked_at = _coerce_dt(row.get("checked_at"))
        if not checked_at:
            continue
        by_day.setdefault(checked_at.date(), []).append(dict(row))

    summary: list[dict[str, Any]] = []
    for offset in range(bounded_days):
        day = start_day + timedelta(days=offset)
        events = by_day.get(day, [])
        if not events:
            summary.append(
                {
                    "date": day.isoformat(),
                    "status": "unknown",
                    "severity": "info",
                    "checks": 0,
                    "failures": 0,
                    "warnings": 0,
                    "message": None,
                    "last_checked_at": None,
                }
            )
            continue

        dominant = max(events, key=lambda item: STATUS_WEIGHT.get(str(item.get("status") or "unknown"), 0))
        last = events[-1]
        failures = sum(1 for item in events if str(item.get("status") or "").lower() == "failed")
        warnings = sum(1 for item in events if str(item.get("status") or "").lower() in {"warning", "running"})
        last_checked_at = _coerce_dt(last.get("checked_at"))
        status = normalize_status(dominant.get("status"))
        summary.append(
            {
                "date": day.isoformat(),
                "status": status,
                "severity": severity_for_status(status, dominant.get("severity")),
                "checks": len(events),
                "failures": failures,
                "warnings": warnings,
                "message": str(dominant.get("message") or last.get("message") or "").strip() or None,
                "last_checked_at": last_checked_at.isoformat() if last_checked_at else None,
            }
        )

    return summary
