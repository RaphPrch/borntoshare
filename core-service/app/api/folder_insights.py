"""The measure of a folder (its own job) and the corrections asked to its guardians for the passwords found in it.
Its growth curve and its duplicates with other folders belong to the 5S module (fives-service)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.data.repositories import lookups_repo
from app.api._helpers import ui_data
from app.api.quotas import _audit, _folder
from app.core.db import get_db
from app.services import remediations, scans
from app.services.authorization import actor_from_request, require_admin
from app.data.models.storage_root import StorageRoot

router = APIRouter(prefix="/storage-roots", tags=["storage-roots"])


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


async def _queue_measure(db: Session, root_id: int, by: str | None = None) -> int | None:
    # The scanner of the 5S module when it is on, the worker of the core otherwise
    return await scans.request_measure(db, int(root_id), reason="manual", by=by)


@router.post("/{root_id}/measure")
async def measure_folder(root_id: int, request: Request, db: Session = Depends(get_db)):
    """Measure the folder (size, age, clutter, duplicates) in the background, on the scan queue: read only."""
    folder = _folder(db, request, root_id)
    actor = actor_from_request(request)
    job_id = await _queue_measure(db, int(root_id), actor.display_name)
    from app.services import inbox

    inbox.remember_requester(db, "measure", int(root_id), actor.identity_id)
    _audit(db, request, "storage_root.measure_requested", folder, {"job_id": job_id})
    return ui_data(scans.get(db, int(root_id)))


class MeasurePayload(BaseModel):
    root_ids: list[int] = Field(min_length=1, max_length=500)


@router.post("/measure")
async def measure_folders(payload: MeasurePayload, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    queued: list[int] = []
    failed: list[dict] = []
    for root_id in dict.fromkeys(int(value) for value in payload.root_ids):
        if lookups_repo.storage_root(db, root_id) is None:
            failed.append({"storage_root_id": root_id, "message": "Storage root not found"})
            continue
        try:
            await _queue_measure(db, root_id, actor.display_name)
            queued.append(root_id)
            # A few folders: each end is told in the bell; a large batch would flood it (the tasks panel shows it)
            if len(payload.root_ids) <= 5:
                from app.services import inbox

                inbox.remember_requester(db, "measure", root_id, actor.identity_id)
        except HTTPException as exc:
            failed.append({"storage_root_id": root_id, "message": str(exc.detail)[:200]})
    _audit(db, request, "storage_root.measure_requested", {"id": queued[0] if len(queued) == 1 else 0, "name": f"{len(queued)} folder(s)"},
           {"storage_root_ids": queued, "failed": failed})
    return ui_data({"queued": queued, "failed": failed})


@router.get("/{root_id}/files")
async def list_folder_files(root_id: int, request: Request, path: str | None = None, db: Session = Depends(get_db)):
    """What the folder (or a sub-folder, path relative to it) holds now on its file server: the files right in it,
    biggest first (5S explorer). Read by a worker at the time of the request."""
    from app.services.probe_service import list_storage_root_folder

    _folder(db, request, root_id)
    return ui_data(await list_storage_root_folder(int(root_id), path))


@router.get("/{root_id}/scan")
def get_scan(root_id: int, request: Request, db: Session = Depends(get_db)):
    """The last measure of the folder (running, done, failed; on the server or through SMB)."""
    _folder(db, request, root_id)
    return ui_data({"scan": scans.get(db, int(root_id))})


class StopPayload(BaseModel):
    kind: str = Field(pattern="^(sensitivity|measure)$")


@router.post("/{root_id}/stop")
async def stop_run(root_id: int, payload: StopPayload, request: Request, db: Session = Depends(get_db)):
    """Stop the sensitivity scan or the measure running on this folder: its job is cancelled (the worker skips
    it), the folder no longer shows it running. A measure by the 5S scanner is marked stopped here."""
    import uuid

    from sqlalchemy import text as _text

    from app.api import provisioning_internal
    from app.core.direct_call import call_route

    actor = actor_from_request(request)
    require_admin(actor)
    folder = _folder(db, request, root_id)
    row = lookups_repo.folder_task_state(db, payload.kind, int(root_id))
    if not row or row["status"] != "running":
        return ui_data({"stopped": False})
    reason = f"Stopped by {actor.display_name or 'an administrator'} from the folder"
    if row["job_id"]:
        await call_route(provisioning_internal.cancel_provisioning_job, job_id=int(row["job_id"]), payload={
            "correlation_id": f"stop_{uuid.uuid4().hex}", "reason": reason, "requested_by": actor.display_name or "operator", "source": "ui"})
    if payload.kind == "measure":
        # Measured by the scanner of the 5S module: it is told to stop too (it checks before each batch)
        from app.services import modules

        modules.stop_scan(int(root_id), by=actor.display_name)
        scans.record_failure(db, int(root_id), row["job_id"], reason)
    else:
        from app.services import sensitivity as _sensitivity

        _sensitivity.record_failure(db, int(root_id), row["job_id"], reason)
        db.commit()
    _audit(db, request, "storage_root.run_stopped", folder, {"kind": payload.kind, "job_id": row["job_id"]})
    return ui_data({"stopped": True})



@router.get("/{root_id}/measures")
def list_measures(root_id: int, request: Request, db: Session = Depends(get_db)):
    """The current measure of the folder and the previous ones kept (date, volume, files, duplicates lost)."""
    _folder(db, request, root_id)
    root = lookups_repo.storage_root(db, int(root_id))
    data = root.discovered_permissions_json if root is not None and isinstance(root.discovered_permissions_json, dict) else {}

    def line(at, size, stats):
        stats = stats or {}
        return {"at": at, "bytes": size, "files": stats.get("files"), "wasted": (stats.get("duplicates") or {}).get("wasted_bytes"), "mode": stats.get("mode")}

    return ui_data({"current": line(data.get("content_updated_at"), data.get("content_size_bytes"), data.get("content_stats")) if data.get("content_stats") else None,
                    "previous": [line(item.get("at"), item.get("bytes"), item.get("stats")) for item in data.get("content_previous") or []]})


class RestorePayload(BaseModel):
    index: int = Field(ge=0, le=10)


@router.post("/{root_id}/measures/restore")
def restore_measure(root_id: int, payload: RestorePayload, request: Request, db: Session = Depends(get_db)):
    """Back to a previous measure of the folder (the current one goes to the history)."""
    actor = actor_from_request(request)
    require_admin(actor)
    folder = _folder(db, request, root_id)
    if not scans.restore_previous(db, int(root_id), payload.index):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "MEASURE_NOT_FOUND", "message": "No such previous measure"})
    _audit(db, request, "storage_root.measure_restored", folder, {"index": payload.index})
    return ui_data({"restored": True})
