from __future__ import annotations

import logging
from typing import Any

from app.core.logging import get_logger, log_event
from app.services.activity_store_db import create_event, list_by_target, list_latest

logger = get_logger("dal.activity")


def list_activity_latest(*, limit: int = 100, business_only: bool = False) -> list[dict[str, Any]]:
    try:
        return list_latest(limit=limit, business_only=business_only)
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "DAL_ACTIVITY_LIST_FAILED",
            action="activity_list_latest",
            outcome="error",
            business_only=bool(business_only),
            message=str(exc),
        )
        return []


def list_activity_by_target(*, target_type: str, target_id: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
    try:
        tid = None if target_id is None else str(target_id)
        return list_by_target(target_type=str(target_type), target_id=tid, limit=limit)
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "DAL_ACTIVITY_LIST_FAILED",
            action="activity_list_by_target",
            target=target_type,
            outcome="error",
            message=str(exc),
        )
        return []


def list_activity_by_actor(*, actor_id: int, limit: int = 200) -> list[dict[str, Any]]:
    # Actor filter not required for Zone UI; keep best-effort with metadata scan later.
    # For now, return latest and let caller filter in UI if needed.
    try:
        events = list_latest(limit=limit)
        aid = str(actor_id)
        return [e for e in events if str(e.get("actor_id") or "") == aid]
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "DAL_ACTIVITY_LIST_FAILED",
            action="activity_list_by_actor",
            actor_id=actor_id,
            outcome="error",
            message=str(exc),
        )
        return []


def create_activity_event(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return create_event(payload)
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "DAL_ACTIVITY_CREATE_FAILED",
            action="activity_create",
            outcome="error",
            message=str(exc),
        )
        return {"ok": False, "error": "activity_create_failed"}


def write_activity_event(
    *,
    actor_type: str,
    actor_id: int | str | None,
    actor_display: str | None,
    action: str,
    outcome: str,
    target_type: str | None,
    target_id: int | str | None,
    target_display: str | None,
    context_json: dict[str, Any] | None,
    correlation_id: str | None,
) -> dict[str, Any]:
    """Adapter used by activity logging call sites."""
    metadata: dict[str, Any] = dict(context_json or {}) if isinstance(context_json, dict) else {}
    if actor_display is not None:
        metadata["actor_display"] = actor_display
    if target_display is not None:
        metadata["target_display"] = target_display

    payload: dict[str, Any] = {
        "action": action,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "entity_type": target_type,
        "entity_id": target_id,
        "result": outcome,
        "metadata_json": metadata,
        "correlation_id": correlation_id,
    }
    return create_activity_event(payload)
