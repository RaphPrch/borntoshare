"""Quotas of the governed folders (FSRM on the Windows file server) and the requests to raise them.

- an administrator sets, changes or removes the quota of a folder: a job applies it on the server and reads it back;
- the guardians of the folder (and the administrators) read it again and ask for more room, with a reason;
- an administrator approves (the new limit goes to the server at once) or refuses with a note.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import quotas
from app.services.activity_log import log_activity
from app.services.authorization import (
    actor_from_request,
    filter_storage_root_rows,
    is_platform_administrator,
    require_admin,
    require_storage_roots_index,
)

router = APIRouter(tags=["quotas"])


def _refuse(code: str, message: str, status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error_code": code, "message": message, **extra})


def _folder(db: Session, request: Request, root_id: int) -> dict[str, Any]:
    """The folder, when the actor may see it (administrator, guardian or backup guardian)."""
    from app.data.models.storage_root import StorageRoot

    actor = actor_from_request(request)
    require_storage_roots_index(db, actor)
    root = db.get(StorageRoot, int(root_id))
    if root is None or not filter_storage_root_rows(db, actor, [{"storage_root_id": int(root_id)}]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    return {"id": int(root.id), "name": root.name, "root_path": root.root_path}


def _audit(db: Session, request: Request, action: str, folder: dict[str, Any], context: dict[str, Any], outcome: str = "success") -> None:
    actor = actor_from_request(request)
    log_activity(
        db,
        actor_type="user" if actor.identity_id is not None else "system",
        actor_id=actor.identity_id,
        actor_display=actor.display_name,
        action=action,
        outcome=outcome,
        target_type="storage_root",
        target_id=str(folder["id"]),
        target_display=str(folder.get("root_path") or folder.get("name") or folder["id"]),
        context_json=context,
        correlation_id=(request.headers.get("x-request-id") or None),
    )


async def _submit(root_id: int, *, protocol: str, target: dict[str, Any]) -> int | None:
    from app.services.probe_service import submit_probe_run

    job = await submit_probe_run({
        "kind": "folder", "protocol": protocol, "scope": "write" if protocol == "quota-apply" else "read",
        "target": {"storage_root_id": int(root_id), **target},
        "options": {"timeout_sec": 90},
        "context": {"storage_root_id": int(root_id), "ui_origin": "folder_quota"},
    })
    return int(job.get("job_id") or 0) or None


async def apply_quota(db: Session, root_id: int, *, limit_bytes: int, soft: bool, warn_percent: int, by: str | None) -> int | None:
    job_id = await _submit(root_id, protocol="quota-apply", target={"operation": "set", "limit_bytes": int(limit_bytes),
                                                                     "soft": bool(soft), "warn_percent": int(warn_percent)})
    quotas.mark_pending(db, root_id, operation="set", job_id=job_id, by=by, limit_bytes=limit_bytes, soft=soft, warn_percent=warn_percent)
    return job_id


@router.get("/storage-roots/{root_id}/quota")
def get_quota(root_id: int, request: Request, db: Session = Depends(get_db)):
    """The quota of the folder on its server, its pending request and the last decisions."""
    _folder(db, request, root_id)
    return ui_data(quotas.get(db, int(root_id)))


class QuotaPayload(BaseModel):
    limit_bytes: int = Field(ge=quotas.MIN_LIMIT, le=quotas.MAX_LIMIT)
    soft: bool = False
    warn_percent: int = Field(default=85, ge=50, le=100)


@router.put("/storage-roots/{root_id}/quota")
async def set_quota(root_id: int, payload: QuotaPayload, request: Request, db: Session = Depends(get_db)):
    """Set or change the quota of the folder on its file server (FSRM)."""
    actor = actor_from_request(request)
    require_admin(actor)
    folder = _folder(db, request, root_id)
    current = quotas.get_quota(db, root_id) or {}
    if current.get("status") == "pending" and current.get("pending_operation") in {"set", "remove"}:
        raise _refuse("QUOTA_CHANGE_PENDING", "A change of this quota is already on its way to the server", status.HTTP_409_CONFLICT)
    used = current.get("used_bytes")
    if used is not None and not payload.soft and payload.limit_bytes < int(used):
        raise _refuse("QUOTA_BELOW_USAGE", "The folder already uses more than this: a hard quota below its use would block every write",
                      used_bytes=int(used))
    job_id = await apply_quota(db, root_id, limit_bytes=payload.limit_bytes, soft=payload.soft, warn_percent=payload.warn_percent,
                               by=actor.display_name)
    _audit(db, request, "storage_root.quota_set", folder, {
        "limit_bytes": payload.limit_bytes, "limit": quotas.describe(payload.limit_bytes), "soft": payload.soft,
        "warn_percent": payload.warn_percent, "previous_limit_bytes": current.get("limit_bytes"), "job_id": job_id,
    })
    return ui_data(quotas.get(db, root_id))


@router.delete("/storage-roots/{root_id}/quota")
async def remove_quota(root_id: int, request: Request, db: Session = Depends(get_db)):
    """Remove the quota of the folder from its file server."""
    actor = actor_from_request(request)
    require_admin(actor)
    folder = _folder(db, request, root_id)
    current = quotas.get_quota(db, root_id)
    if not current or current.get("status") == "none":
        raise _refuse("QUOTA_NOT_FOUND", "This folder has no quota", status.HTTP_404_NOT_FOUND)
    job_id = await _submit(root_id, protocol="quota-apply", target={"operation": "remove"})
    quotas.mark_pending(db, root_id, operation="remove", job_id=job_id, by=actor.display_name)
    _audit(db, request, "storage_root.quota_removed", folder, {"previous_limit_bytes": current.get("limit_bytes"),
                                                               "limit": quotas.describe(current.get("limit_bytes")), "job_id": job_id})
    return ui_data(quotas.get(db, root_id))


@router.post("/storage-roots/{root_id}/quota/refresh")
async def refresh_quota(root_id: int, request: Request, db: Session = Depends(get_db)):
    """Read the quota on the server again (its use moves with the files)."""
    _folder(db, request, root_id)
    job_id = await _submit(root_id, protocol="quota-read", target={})
    quotas.mark_pending(db, root_id, operation="read", job_id=job_id, by=None)
    return ui_data(quotas.get(db, root_id))


class QuotaRequestPayload(BaseModel):
    requested_limit_bytes: int = Field(ge=quotas.MIN_LIMIT, le=quotas.MAX_LIMIT)
    reason: str = Field(min_length=1, max_length=500)


@router.post("/storage-roots/{root_id}/quota/requests")
def request_more(root_id: int, payload: QuotaRequestPayload, request: Request, db: Session = Depends(get_db)):
    """Ask for more room in the folder: an administrator decides."""
    actor = actor_from_request(request)
    folder = _folder(db, request, root_id)
    reason = payload.reason.strip()
    if len(reason) < 5:
        raise _refuse("QUOTA_REASON_REQUIRED", "Say why the folder needs more room")
    current = quotas.get_quota(db, root_id) or {}
    if current.get("status") != "applied" or not current.get("limit_bytes"):
        raise _refuse("QUOTA_NOT_FOUND", "This folder has no quota to raise", status.HTTP_404_NOT_FOUND)
    if payload.requested_limit_bytes <= int(current["limit_bytes"]):
        raise _refuse("QUOTA_REQUEST_NOT_HIGHER", "Ask for more than the current quota", current_limit_bytes=int(current["limit_bytes"]))
    if quotas.pending_request(db, root_id):
        raise _refuse("QUOTA_REQUEST_PENDING", "A request for this folder is already waiting for a decision", status.HTTP_409_CONFLICT)
    created = quotas.create_request(db, root_id, requested_limit_bytes=payload.requested_limit_bytes, reason=reason,
                                    identity_id=actor.identity_id, by=actor.display_name)
    _audit(db, request, "storage_root.quota_requested", folder, {
        "request_id": created["id"], "requested_limit_bytes": payload.requested_limit_bytes,
        "requested": quotas.describe(payload.requested_limit_bytes), "current": quotas.describe(current["limit_bytes"]), "reason": reason,
    })
    return ui_data(quotas.get(db, root_id))


@router.get("/quota-requests")
def list_quota_requests(request: Request, status_filter: Literal["pending", "approved", "rejected", "cancelled", "all"] = "pending",
                        db: Session = Depends(get_db)):
    """Requests to raise a quota (administrators: all of them; guardians: those of their folders)."""
    actor = actor_from_request(request)
    rows = quotas.list_requests(db, None if status_filter == "all" else status_filter)
    if not is_platform_administrator(actor):
        allowed = {int(row["storage_root_id"]) for row in filter_storage_root_rows(db, actor, [{"storage_root_id": r["storage_root_id"]} for r in rows])}
        rows = [row for row in rows if row["storage_root_id"] in allowed]
    return ui_data(rows)


class QuotaDecisionPayload(BaseModel):
    decision: Literal["approve", "reject", "cancel"]
    note: str | None = Field(default=None, max_length=500)


@router.post("/quota-requests/{request_id}/decision")
async def decide_quota_request(request_id: int, payload: QuotaDecisionPayload, request: Request, db: Session = Depends(get_db)):
    """Approve (the new limit goes to the server), refuse (with a note) or cancel (the person who asked)."""
    actor = actor_from_request(request)
    item = quotas.get_request(db, request_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quota request not found")
    folder = _folder(db, request, item["storage_root_id"])
    if item["status"] != "pending":
        raise _refuse("QUOTA_REQUEST_DECIDED", "This request was already decided", status.HTTP_409_CONFLICT)
    note = (payload.note or "").strip() or None
    if payload.decision == "cancel":
        if not is_platform_administrator(actor) and item["requested_by_identity_id"] != actor.identity_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the person who asked can cancel the request")
        quotas.decide_request(db, request_id, status="cancelled", by=actor.display_name, note=note)
        _audit(db, request, "storage_root.quota_request_cancelled", folder, {"request_id": request_id})
        return ui_data(quotas.get(db, item["storage_root_id"]))
    require_admin(actor)
    if payload.decision == "reject":
        if not note or len(note) < 3:
            raise _refuse("QUOTA_NOTE_REQUIRED", "Say why the request is refused: the person who asked reads it")
        quotas.decide_request(db, request_id, status="rejected", by=actor.display_name, note=note)
        _audit(db, request, "storage_root.quota_request_rejected", folder, {
            "request_id": request_id, "requested": quotas.describe(item["requested_limit_bytes"]), "note": note,
            "requested_by": item["requested_by"]})
        return ui_data(quotas.get(db, item["storage_root_id"]))
    current = quotas.get_quota(db, item["storage_root_id"]) or {}
    if current.get("status") == "pending" and current.get("pending_operation") in {"set", "remove"}:
        raise _refuse("QUOTA_CHANGE_PENDING", "A change of this quota is already on its way to the server", status.HTTP_409_CONFLICT)
    job_id = await apply_quota(db, item["storage_root_id"], limit_bytes=item["requested_limit_bytes"], soft=bool(current.get("soft")),
                               warn_percent=int(current.get("warn_percent") or 85), by=actor.display_name)
    quotas.decide_request(db, request_id, status="approved", by=actor.display_name, note=note)
    _audit(db, request, "storage_root.quota_request_approved", folder, {
        "request_id": request_id, "requested": quotas.describe(item["requested_limit_bytes"]),
        "requested_limit_bytes": item["requested_limit_bytes"], "previous": quotas.describe(current.get("limit_bytes")),
        "requested_by": item["requested_by"], "job_id": job_id})
    return ui_data(quotas.get(db, item["storage_root_id"]))
