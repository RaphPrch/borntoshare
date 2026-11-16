"""Access review campaigns (Access Management › Reviews): open, list, decide, close. The removals are applied by the
orchestration route (api/governance/access_reviews.py), which revokes the requests through the usual path."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import access_reviews
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, admin_only, admin_or_guardian

router = APIRouter(prefix="/access-reviews", tags=["access-reviews"])
internal_router = APIRouter(prefix="/internal/access-reviews", tags=["internal-access-reviews"])


def _audit(request: Request, action: str, review_id: int, name: str, context: dict[str, Any], outcome: str = "success") -> None:
    actor = actor_from_request(request)
    log_activity(None, actor_type="user" if actor.identity_id is not None else "system", actor_id=actor.identity_id,
                 actor_display=actor.display_name, action=action, outcome=outcome, target_type="access_review",
                 target_id=str(review_id), target_display=name, context_json={"review": name, **context},
                 correlation_id=request.headers.get("x-request-id") or None)


class OpenReview(BaseModel):
    name: str = Field(min_length=2, max_length=190)
    root_ids: list[int] | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None


class Decisions(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=5000)
    decision: str | None = Field(default=None, pattern="^(keep|revoke)$")
    note: str | None = Field(default=None, max_length=500)


class Outcome(BaseModel):
    outcome: str = Field(pattern="^(revoked|manual|failed)$")
    detail: str | None = Field(default=None, max_length=500)


@router.get("", dependencies=[Depends(admin_or_guardian)])
def list_access_reviews(request: Request, db: Session = Depends(get_db)):
    """The campaigns and their progress (a guardian sees the part of their folders)."""
    return ui_data(access_reviews.list_reviews(db, actor_from_request(request)))


@router.post("", dependencies=[Depends(admin_only)])
def open_access_review(payload: OpenReview, request: Request, db: Session = Depends(get_db)):
    """Open a campaign on every governed folder (or these ones): every person who reaches them now is listed."""
    actor = actor_from_request(request)
    due = payload.due_at.replace(tzinfo=None) if payload.due_at else None
    result = access_reviews.open_review(db, actor, name=payload.name, root_ids=payload.root_ids, due_at=due)
    notified = access_reviews.notify_guardians(db, result["id"], payload.name, result["root_ids"], due)
    _audit(request, "access_review.opened", result["id"], payload.name, {"count": result["items"], "folders": result["folders"], "guardians": notified})
    return ui_data({**result, "guardians_notified": notified})


@router.get("/{review_id}", dependencies=[Depends(admin_or_guardian)])
def get_access_review(review_id: int, request: Request, db: Session = Depends(get_db)):
    return ui_data(access_reviews.items(db, actor_from_request(request), review_id))


@router.post("/{review_id}/decisions", dependencies=[Depends(admin_or_guardian)])
def decide_access_review(review_id: int, payload: Decisions, request: Request, db: Session = Depends(get_db)):
    """Keep or remove accesses (on the folders this person guards); the removals are applied separately."""
    actor = actor_from_request(request)
    changed = access_reviews.decide(db, actor, review_id, payload.item_ids, payload.decision, payload.note)
    review = access_reviews.items(db, actor, review_id)["review"]
    _audit(request, "access_review.decided", review_id, review["name"], {"count": changed, "decision": payload.decision or "reset"})
    return ui_data({"changed": changed})


@router.post("/{review_id}/close", dependencies=[Depends(admin_only)])
def close_access_review(review_id: int, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    name = access_reviews.items(db, actor, review_id)["review"]["name"]
    result = access_reviews.close_review(db, actor, review_id)
    _audit(request, "access_review.closed", review_id, name, result)
    return ui_data(result)


@router.get("/{review_id}/removals", dependencies=[Depends(admin_or_guardian)])
def list_access_review_removals(review_id: int, request: Request, db: Session = Depends(get_db)):
    """The accesses decided « remove » and not applied yet (used by the orchestration route)."""
    return ui_data(access_reviews.pending_removals(db, actor_from_request(request), review_id))


@internal_router.post("/items/{item_id}/outcome")
def record_access_review_outcome(item_id: int, payload: Outcome, db: Session = Depends(get_db)):
    """What became of a removal (revoked, to handle by hand, failed): written by the orchestration route only."""
    access_reviews.record_outcome(db, item_id, payload.outcome, payload.detail)
    return ui_data({"recorded": True})
