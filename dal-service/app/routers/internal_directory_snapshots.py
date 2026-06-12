from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.repositories.directory_snapshots_repo import DirectorySnapshotsRepo
from app.services.directory_effective_memberships_service import DirectoryEffectiveMembershipsService
from app.services.directory_projection_service import DirectoryProjectionService
from app.schemas.directory_snapshots import (
    DirectorySnapshotActivateRequest,
    DirectorySnapshotBulkUpsertRequest,
    DirectorySnapshotRunRequest,
    DirectorySnapshotRunResponse,
    DirectorySnapshotStatusPatchRequest,
)
from app.security.internal_auth import require_internal


router = APIRouter(
    prefix="/internal/directory-snapshots",
    tags=["internal-directory-snapshots"],
)


@router.post("/runs", response_model=DirectorySnapshotRunResponse, dependencies=[require_internal({"jobs:write"})])
def create_snapshot_run(payload: DirectorySnapshotRunRequest, db: Session = Depends(get_db)):
    requested_mode = str(payload.mode or "").strip().lower()
    try:
        summary = {
            "mode": requested_mode or "auto",
            "requested_mode": requested_mode or "auto",
            "phase": "queued",
            "deferred": True,
            "force_full": bool(payload.force_full),
        }
        repo = DirectorySnapshotsRepo(db)
        created = repo.create_run(
            identity_source_id=int(payload.identity_source_id),
            initiated_by=payload.initiated_by,
            snapshot_source=payload.snapshot_source,
            correlation_id=payload.correlation_id,
            summary_json=summary,
        )
        row = repo.patch_status(
            snapshot_id=int(created.get("id") or 0),
            status="QUEUED",
            summary_json=summary,
            error_message=None,
        ) or created
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create snapshot run")

    if "status" in row and "version" in row:
        snapshot_id = int(row["id"])
        identity_source_id = int(row["identity_source_id"])
        version = int(row["version"])
        status_value = str(row["status"])
    else:
        repo = DirectorySnapshotsRepo(db)
        snapshot_id = int(row["snapshot_id"])
        loaded = repo.get(snapshot_id)
        if not loaded:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Snapshot created but not readable")
        identity_source_id = int(loaded["identity_source_id"])
        version = int(loaded["version"])
        status_value = str(loaded["status"])

    return DirectorySnapshotRunResponse(
        snapshot_id=snapshot_id,
        identity_source_id=identity_source_id,
        version=version,
        status=status_value,
    )


@router.get("/runs", dependencies=[require_internal({"jobs:read"})])
def list_snapshot_runs(
    identity_source_id: int | None = Query(default=None, gt=0),
    status_value: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    repo = DirectorySnapshotsRepo(db)
    return repo.list_runs(
        identity_source_id=identity_source_id,
        status=status_value,
        limit=limit,
    )


@router.get("/runs/{snapshot_id}", dependencies=[require_internal({"jobs:read"})])
def get_snapshot_run(snapshot_id: int, db: Session = Depends(get_db)):
    repo = DirectorySnapshotsRepo(db)
    row = repo.get(snapshot_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")
    return row


@router.patch("/runs/{snapshot_id}/status", dependencies=[require_internal({"jobs:write"})])
def patch_snapshot_status(
    snapshot_id: int,
    payload: DirectorySnapshotStatusPatchRequest,
    db: Session = Depends(get_db),
):
    repo = DirectorySnapshotsRepo(db)
    row = repo.patch_status(
        snapshot_id=snapshot_id,
        status=payload.status,
        summary_json=payload.summary_json,
        error_message=payload.error_message,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")
    return row


@router.post("/runs/{snapshot_id}/bulk", dependencies=[require_internal({"jobs:write"})])
def bulk_upsert_snapshot_payload(
    snapshot_id: int,
    payload: DirectorySnapshotBulkUpsertRequest,
    db: Session = Depends(get_db),
):
    repo = DirectorySnapshotsRepo(db)
    snapshot = repo.get(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")
    return repo.bulk_upsert(
        snapshot_id=snapshot_id,
        users=[item.model_dump() for item in payload.users],
        groups=[item.model_dump() for item in payload.groups],
        memberships=[item.model_dump() for item in payload.memberships],
    )


@router.post("/runs/{snapshot_id}/activate", dependencies=[require_internal({"jobs:write", "profiles:write"})])
def activate_snapshot_run(
    snapshot_id: int,
    payload: DirectorySnapshotActivateRequest,
    db: Session = Depends(get_db),
):
    row = DirectoryProjectionService(db).activate_snapshot(snapshot_id=snapshot_id, activated_by=payload.activated_by)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    if bool(payload.rebuild_effective_memberships):
        DirectoryEffectiveMembershipsService(db).rebuild_for_snapshot(snapshot_id=int(snapshot_id))

    return row


@router.post(
    "/rebuild-effective-memberships",
    dependencies=[require_internal({"jobs:write", "profiles:write"})],
)
def rebuild_effective_memberships(
    identity_source_id: int | None = Query(default=None, gt=0),
    snapshot_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    svc = DirectoryEffectiveMembershipsService(db)
    if snapshot_id is not None:
        return svc.rebuild_for_snapshot(snapshot_id=int(snapshot_id))
    if identity_source_id is not None:
        return svc.rebuild_for_identity_source(identity_source_id=int(identity_source_id))
    return {"results": svc.rebuild_all_active()}


@router.get("/runs/{snapshot_id}/search", dependencies=[require_internal({"jobs:read"})])
def search_snapshot_principals(
    snapshot_id: int,
    q: str | None = Query(default=None),
    principal_type: str = Query(default="all"),
    dn: str | None = Query(default=None),
    search_scope: str = Query(default="subtree"),
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    repo = DirectorySnapshotsRepo(db)
    snapshot = repo.get(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")
    return {
        "items": repo.search(
            snapshot_id=snapshot_id,
            query=q,
            principal_type=principal_type,
            base_dn=dn,
            search_scope=search_scope,
            limit=limit,
            enabled_only=enabled_only,
        )
    }
