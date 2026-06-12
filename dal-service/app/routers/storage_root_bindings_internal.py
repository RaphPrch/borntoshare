from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.routers._helpers import ui_data
from app.security.internal_auth import require_internal
from app.services.storage_root_binding_materialization_service import (
    repair_all_root_bindings,
    repair_missing_root_bindings,
    resync_roots_for_zone,
)


router = APIRouter(prefix="/internal", tags=["internal-storage-root-bindings"])


@router.post(
    "/storage-roots/{storage_root_id}/repair-bindings",
    dependencies=[require_internal({"profiles:write"})],
)
def repair_storage_root_bindings(storage_root_id: int, db: Session = Depends(get_db)):
    report = repair_missing_root_bindings(
        db,
        storage_root_id=int(storage_root_id),
        commit=True,
    )
    payload = report.to_dict()
    return ui_data(payload, meta={"storage_root_id": int(storage_root_id)})


@router.post(
    "/zones/{zone_id}/resync-root-bindings",
    dependencies=[require_internal({"profiles:write"})],
)
def resync_zone_root_bindings(zone_id: int, db: Session = Depends(get_db)):
    report = resync_roots_for_zone(
        db,
        zone_id=int(zone_id),
        replace_stale=True,
        commit=True,
    )
    return ui_data(report, meta={"zone_id": int(zone_id), "count": int(report.get("roots_count") or 0)})


@router.post(
    "/storage-roots/repair-all-bindings",
    dependencies=[require_internal({"profiles:write"})],
)
def repair_all_storage_root_bindings(db: Session = Depends(get_db)):
    report = repair_all_root_bindings(
        db,
        replace_stale=True,
        commit=True,
    )
    return ui_data(report, meta={"count": int(report.get("roots_count") or 0)})

