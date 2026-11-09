"""What a folder tells over time: its growth curve (and when its quota will be full), and the corrections asked to
its guardians for the passwords found in it."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.api.quotas import _audit, _folder
from app.core.db import get_db
from app.services import content_history, quotas, remediations
from app.services.authorization import actor_from_request, require_admin

router = APIRouter(prefix="/storage-roots", tags=["storage-roots"])


@router.get("/{root_id}/content-history")
def get_content_history(root_id: int, request: Request, db: Session = Depends(get_db)):
    """The measures of the last 180 days, the pace (bytes per day) and the date the quota will be full."""
    _folder(db, request, root_id)
    quota = quotas.get_quota(db, root_id) or {}
    limit = quota.get("limit_bytes") if quota.get("status") == "applied" else None
    return ui_data(content_history.summary(db, int(root_id), limit))


@router.get("/{root_id}/remediation")
def get_remediation(root_id: int, request: Request, db: Session = Depends(get_db)):
    """The correction in progress for the passwords of the folder, and the last ones."""
    _folder(db, request, root_id)
    return ui_data({"current": remediations.current(db, root_id), "history": remediations.history(db, root_id)})


class RemediationPayload(BaseModel):
    due_days: int = Field(default=14, ge=1, le=90)
    note: str | None = Field(default=None, max_length=500)


@router.post("/{root_id}/remediation")
def ask_remediation(root_id: int, payload: RemediationPayload, request: Request, db: Session = Depends(get_db)):
    """Ask the guardians to remove or move the files holding passwords, before a due date."""
    actor = actor_from_request(request)
    require_admin(actor)
    folder = _folder(db, request, root_id)
    if remediations.current(db, root_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "error_code": "REMEDIATION_PENDING", "message": "A correction is already asked for this folder"})
    if not remediations.password_paths(db, root_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "error_code": "REMEDIATION_NOTHING_TO_FIX", "message": "The last scan found no password in this folder"})
    item = remediations.create(db, root_id, due_days=payload.due_days, note=(payload.note or "").strip() or None, by=actor.display_name)
    _audit(db, request, "storage_root.remediation_requested", folder, {
        "remediation_id": item["id"], "files": item["files_at_request"], "due_at": item["due_at"], "note": item.get("note"),
        "notified": item.get("notified")})
    return ui_data({"current": remediations.current(db, root_id), "history": remediations.history(db, root_id)})


@router.post("/{root_id}/remediation/cancel")
def cancel_remediation(root_id: int, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    folder = _folder(db, request, root_id)
    item = remediations.current(db, root_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "REMEDIATION_NOT_FOUND", "message": "No correction in progress"})
    remediations.close(db, item["id"], status="cancelled", by=actor.display_name)
    _audit(db, request, "storage_root.remediation_cancelled", folder, {"remediation_id": item["id"]})
    return ui_data({"current": None, "history": remediations.history(db, root_id)})
