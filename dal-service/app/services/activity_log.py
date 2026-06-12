from __future__ import annotations

import logging
from typing import Any
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.services.activity_bridge import write_activity_event

logger = get_logger(__name__)


_activity_logged_in_request: ContextVar[bool] = ContextVar(
    "activity_logged_in_request",
    default=False,
)
_activity_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dal-activity")


def _write_activity_safe(payload: dict[str, Any]) -> None:
    try:
        result = write_activity_event(**payload)
        if not bool((result or {}).get("ok", True)):
            log_event(
                logger,
                logging.WARNING,
                "DAL_ACTIVITY_WRITE_REJECTED",
                action="activity_write",
                outcome="rejected",
                details={"result": result},
            )
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "DAL_ACTIVITY_WRITE_FAILED",
            action="activity_write",
            outcome="error",
            message=str(exc),
        )


def reset_activity_marker() -> None:
    _activity_logged_in_request.set(False)


def has_activity_marker() -> bool:
    return bool(_activity_logged_in_request.get())


def log_activity(
    db: Session | None,
    *,
    actor_type: str,
    actor_id: int | str | None,
    actor_display: str | None,
    action: str,
    outcome: str,
    target_type: str | None = None,
    target_id: int | str | None = None,
    target_display: str | None = None,
    context_json: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    background: bool = True,
) -> dict[str, Any]:
    """Bridge DAL business activity into wizard logging audit DB (SecNum L2)."""

    _ = db  # kept for backward-compatible call sites
    payload = {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "actor_display": actor_display,
        "action": action,
        "outcome": outcome,
        "target_type": target_type,
        "target_id": target_id,
        "target_display": target_display,
        "context_json": context_json,
        "correlation_id": correlation_id,
    }

    _activity_logged_in_request.set(True)

    if not background:
        _write_activity_safe(payload)
        return {"ok": True, "queued": False}

    # Non-blocking fire-and-forget:
    # activity bridge outages must never block critical write endpoints
    # (identity-sources create/update, access profiles, etc.).
    _activity_executor.submit(_write_activity_safe, payload)
    return {"ok": True, "queued": True}
