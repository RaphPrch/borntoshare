"""What the 5S module (fives-service) asks the core, with the shared internal token: is it licensed and on, and
which folders may this person see (with what the core knows of them). The module never reads this database."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import features
from app.services.authorization import actor_from_request, filter_storage_root_rows, require_storage_roots_index

router = APIRouter(prefix="/internal/modules/fives", tags=["internal-modules"])

# What the module needs of a folder (the rest stays in the core)
FIELDS = (
    "storage_root_id", "storage_root_name", "root_path", "dfs_path", "zone_id", "zone_name", "storage_endpoint_id", "storage_endpoint_name",
    "content_size_bytes", "content_updated_at", "content_files", "cold_1y_bytes", "cold_3y_bytes", "junk_files", "junk_bytes", "last_modified_at",
    "dup_wasted_bytes", "dup_groups", "guardians_count", "tags", "quota_status", "quota_limit_bytes", "quota_used_bytes", "quota_used_percent",
    "quota_warn_percent", "quota_pending_requests", "sensitive_files", "password_files", "key_files", "remediation_status",
    "inheritance_broken", "open_alerts_error_count", "last_probe_status", "pending_validation_count", "measure_status",
)


@router.get("/license")
def license_state(db: Session = Depends(get_db)):
    state = next((item for item in features.state(db)["features"] if item["key"] == "fives"), {})
    limits = {}
    for lic in features.state(db)["licenses"]:
        if "fives" in lic["features"] and not lic["expired"]:
            limits.update(lic.get("limits") or {})
    return ui_data({"licensed": bool(state.get("licensed")), "enabled": bool(state.get("enabled")), "expires_on": state.get("expires_on"), "limits": limits})


@router.get("/folders")
def folders(request: Request, zone_id: int | None = None, root_id: int | None = None, db: Session = Depends(get_db)):
    """The folders of the person forwarded by the module (x-identity-id, x-roles): administrators all, guardians theirs."""
    from app.services.policies import folder_rows

    actor = actor_from_request(request)
    require_storage_roots_index(db, actor)
    rows = filter_storage_root_rows(db, actor, folder_rows(db))
    if zone_id:
        rows = [row for row in rows if int(row.get("zone_id") or 0) == int(zone_id)]
    if root_id:
        rows = [row for row in rows if int(row.get("storage_root_id") or 0) == int(root_id)]
    ids = [int(row.get("storage_root_id") or 0) for row in rows]
    scanned: dict[int, object] = {}
    if ids:
        scanned = {int(root): at for root, at in db.execute(
            text("SELECT storage_root_id, scanned_at FROM storage_root_sensitivity WHERE scanned_at IS NOT NULL AND storage_root_id IN :ids")
            .bindparams(bindparam("ids", expanding=True)), {"ids": ids}).all()}
    out = []
    for row in rows:
        item = {key: row.get(key) for key in FIELDS}
        at = scanned.get(int(row.get("storage_root_id") or 0))
        item["sensitivity_scanned_at"] = at.isoformat() + "Z" if at else None
        out.append(item)
    return ui_data(jsonable_encoder(out))
