from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.routers._helpers import ui_action
from app.services.activity_bridge import create_activity_event as create_activity_event_db


router = APIRouter(prefix="/activity", tags=["activity"])


class ActivityEventCreate(BaseModel):
    action: str = Field(..., min_length=1, max_length=128)
    outcome: str = Field("success", min_length=1, max_length=16)
    severity: str | None = Field(default=None, min_length=1, max_length=20)

    actor_type: str = Field("system", min_length=1, max_length=16)
    actor_id: int | str | None = None
    actor_display: str | None = None

    target_type: str | None = Field(None, max_length=64)
    target_id: int | str | None = None
    target_display: str | None = None

    zone_id: int | str | None = None
    root_id: int | str | None = None
    endpoint_id: int | str | None = None
    source_service: str | None = None

    metadata_json: dict[str, Any] | None = None

    context_json: dict[str, Any] | None = None
    correlation_id: str | None = None


@router.post("/events")
def create_activity_event_route(payload: ActivityEventCreate):
    data = payload.model_dump(exclude_none=True)

    ev = create_activity_event_db(data if isinstance(data, dict) else {})
    if not isinstance(ev, dict):
        return ui_action(ok=False, message="activity.event.create_failed")
    return ui_action(
        ok=bool(ev.get("ok", False)),
        action_id=ev.get("id"),
        message="activity.event.created",
    )
