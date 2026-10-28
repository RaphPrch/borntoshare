"""Log retention (Advanced Settings › Logging): purge and log level.

Purge: audit events (logging database) and health events (main database) older than the retention.
The purge is itself written to the audit log, with what it removed. Run by « Purge old logs » and,
when retention is enabled, once a day by the infrastructure scheduler.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

BATCH = 5000
DAILY_SECONDS = 24 * 3600

_last_auto_purge = 0.0


def logging_settings(db: Session) -> dict[str, Any]:
    from app.api.advanced_settings import _read_payload

    cfg = (_read_payload(db) or {}).get("logging") or {}
    return {
        "level": str(cfg.get("level") or "INFO").upper(),
        "retentionEnabled": bool(cfg.get("retentionEnabled", True)),
        "retentionDays": max(1, min(int(cfg.get("retentionDays") or 180), 3650)),
    }


def _delete_older(session: Session, table: str, column: str, days: int) -> int:
    """Batched deletes: short locks on a large table."""
    total = 0
    while True:
        deleted = session.execute(
            text(f"DELETE FROM {table} WHERE {column} < UTC_TIMESTAMP() - INTERVAL :days DAY LIMIT {BATCH}"),
            {"days": int(days)},
        ).rowcount or 0
        session.commit()
        total += int(deleted)
        if deleted < BATCH:
            return total


def purge_logs(db: Session, *, days: int | None = None, trigger: str, actor_display: str | None = None) -> dict[str, Any]:
    from app.core.logging_db import LoggingSessionLocal
    from app.services.activity_log import log_activity

    days = int(days or logging_settings(db)["retentionDays"])
    with LoggingSessionLocal() as logging_db:
        audit = _delete_older(logging_db, "audit_event", "event_time", days)
    health = _delete_older(db, "governance_health_events", "checked_at", days)
    result = {"retention_days": days, "audit_events": audit, "health_events": health}
    log_activity(
        db,
        actor_type="user" if actor_display and trigger == "manual" else "system",
        actor_id=None,
        actor_display=actor_display or "log-retention",
        action="logs.purged",
        outcome="success",
        target_type="logs",
        target_display=f"older than {days} days",
        context_json={**result, "trigger": trigger},
    )
    return result


def auto_purge_if_due(db: Session) -> dict[str, Any] | None:
    """Once a day when retention is enabled (called by the infrastructure scheduler)."""
    global _last_auto_purge
    if time.time() - _last_auto_purge < DAILY_SECONDS:
        return None
    _last_auto_purge = time.time()
    settings = logging_settings(db)
    if not settings["retentionEnabled"]:
        return None
    return purge_logs(db, days=settings["retentionDays"], trigger="schedule")


def apply_log_level(level: str) -> str:
    """core-service log level, same names as the UI (WARN = WARNING)."""
    name = {"WARN": "WARNING"}.get(str(level or "INFO").upper(), str(level or "INFO").upper())
    value = getattr(logging, name, None)
    if not isinstance(value, int):
        return "INFO"
    logging.getLogger().setLevel(value)
    for logger_name in ("core", "app", "uvicorn"):
        logging.getLogger(logger_name).setLevel(value)
    return name
