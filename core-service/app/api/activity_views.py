from __future__ import annotations

from fastapi import APIRouter, Body, Request, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api._helpers import ui_action, ui_list
from app.services.authorization import (
    actor_from_request,
    require_access_request_access,
    require_observability,
    require_storage_root_access,
)
from app.services.activity_bridge import (
    create_activity_event,
    list_activity_by_actor,
    list_activity_by_target,
    list_activity_latest,
)

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/latest")
def get_activity_latest(request: Request, limit: int = 100, business_only: bool = False):
    require_observability(actor_from_request(request))
    rows = list_activity_latest(limit=limit, business_only=business_only)
    payload = rows if isinstance(rows, list) else []
    return ui_list(
        payload,
        meta={
            "limit": int(limit),
            "count": int(len(payload)),
            "business_only": bool(business_only),
        },
    )


@router.get("/search")
def search_activity(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    period: str | None = None,
    module: str | None = None,
    severity: str | None = None,
    outcome: str | None = None,
    actor: str | None = None,
    q: str | None = None,
):
    """Observability › Events: filtered, paginated in the database."""
    from app.services.activity_store_db import search_events

    require_observability(actor_from_request(request))
    hours = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}.get(str(period or ""))
    data = search_events(
        page=page, page_size=page_size, hours=hours, module=module or None, severity=severity or None,
        outcome=outcome or None, actor=actor or None, q=(q or "").strip() or None,
    )
    return ui_list(data["items"], meta={k: data[k] for k in ("total", "page", "page_size", "modules")})


@router.get("/by-target")
def get_activity_by_target(
    request: Request,
    target_type: str,
    target_id: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    actor = actor_from_request(request)
    normalized_target_type = str(target_type or "").strip().lower()
    if normalized_target_type == "storage_root" and int(target_id or 0) > 0:
        require_storage_root_access(db, actor, int(target_id))
    elif normalized_target_type == "access_request" and int(target_id or 0) > 0:
        # Provisioning log of a request: whoever may see the request
        require_access_request_access(db, actor, int(target_id))
    elif normalized_target_type in {"zone", "storage_endpoint", "access_request", "storage_root_access_profile"}:
        require_observability(actor)
    rows = list_activity_by_target(
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )
    payload = rows if isinstance(rows, list) else []
    return ui_list(
        payload,
        meta={
            "target_type": str(target_type),
            "target_id": int(target_id) if target_id is not None else None,
            "limit": int(limit),
            "count": int(len(payload)),
        },
    )


@router.get("/by-actor")
def get_activity_by_actor(request: Request, actor_id: int, limit: int = 200):
    require_observability(actor_from_request(request))
    rows = list_activity_by_actor(actor_id=actor_id, limit=limit)
    payload = rows if isinstance(rows, list) else []
    return ui_list(
        payload,
        meta={
            "actor_id": int(actor_id),
            "limit": int(limit),
            "count": int(len(payload)),
        },
    )


@router.post("/events")
def post_activity_event(payload: dict = Body(default_factory=dict)):
    # Accept a generic dict payload.
    created = create_activity_event(payload if isinstance(payload, dict) else {})
    if not isinstance(created, dict):
        return ui_action(ok=False, message="activity.event.create_failed")
    return ui_action(
        ok=bool(created.get("ok", True)),
        action_id=created.get("id"),
        message="activity.event.created",
    )
