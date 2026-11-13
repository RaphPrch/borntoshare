"""Notification centre of the app (the bell) and the pulse read by the live updates."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session

from app.api._helpers import ui_action, ui_data
from app.core.db import get_db
from app.services import inbox
from app.services.authorization import actor_from_request, is_platform_administrator, signed_in_or_internal

router = APIRouter(prefix="/me", tags=["inbox"])


@router.get("/notifications", dependencies=[Depends(signed_in_or_internal)])
def list_my_notifications(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    if actor.identity_id is None:
        return ui_data({"items": [], "unread": 0})
    return ui_data(inbox.listing(db, actor.identity_id, limit=limit))


@router.post("/notifications/read", dependencies=[Depends(signed_in_or_internal)])
def read_my_notifications(request: Request, body: dict = Body(default_factory=dict), db: Session = Depends(get_db)):
    """Marks the given notices as read ({"ids": [...]}), or all of them ({} or {"all": true})."""
    actor = actor_from_request(request)
    if actor.identity_id is None:
        return ui_action(details={"marked": 0})
    raw = body.get("ids") if isinstance(body, dict) else None
    ids = [int(value) for value in raw if str(value).isdigit()] if isinstance(raw, list) else None
    return ui_action(details={"marked": inbox.mark_read(db, actor.identity_id, ids or None)})


@router.get("/pulse", dependencies=[Depends(signed_in_or_internal)])
def get_my_pulse(request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    return ui_data(inbox.pulse(db, actor.identity_id, admin=is_platform_administrator(actor)))
