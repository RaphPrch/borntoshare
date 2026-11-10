"""What the 5S module (fives-service) asks the core, with the shared internal token: is it licensed and on, and
which folders may this person see (with what the core knows of them). The module never reads this database."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
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
    # The module asks while it runs: licensed and switched on is enough (« enabled » also needs it to answer)
    on = bool(state.get("licensed")) and bool(state.get("switched_on"))
    return ui_data({"licensed": bool(state.get("licensed")), "enabled": on, "expires_on": state.get("expires_on"), "limits": limits})


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


@router.get("/scan-context/{root_id}")
async def scan_context(root_id: int):
    """Where the folder is and with which account the scanner of the module walks it (never the password: it asks
    the secret broker for it)."""
    from fastapi import HTTPException

    from app.api import provisioning_internal
    from app.core.direct_call import call_route
    from app.services.probe_service import _parse_unc_root_path, _probe_credentials

    ctx = await call_route(provisioning_internal.get_storage_root_provisioning_context, storage_root_id=int(root_id))
    if not isinstance(ctx, dict):
        raise HTTPException(status_code=404, detail="Storage root not found")
    host, share, path = _parse_unc_root_path(ctx.get("root_path"))
    username, secret_ref = _probe_credentials({}, ctx)
    windows = str(ctx.get("endpoint_type") or "smb").strip().lower() == "smb"
    return ui_data({"storage_root_id": int(root_id), "host": host, "share": share, "path": path or "", "username": username, "secret_ref": secret_ref,
                    "domain": str(ctx.get("domain_name") or ""), "server_name": (str(ctx.get("endpoint_name") or "").strip() or None) if windows else None,
                    "kdc_host": str(ctx.get("identity_source_host") or "").strip() or None, "endpoint_type": ctx.get("endpoint_type")})


class MeasureResult(BaseModel):
    storage_root_id: int = Field(gt=0)
    status: str = Field(pattern="^(running|done|failed)$")
    stats: dict | None = None
    method: str | None = None
    elapsed_ms: int | None = None
    files: int | None = None
    progress: dict | None = None
    error: str | None = None


@router.post("/measure-result")
def measure_result(payload: MeasureResult, db: Session = Depends(get_db)):
    """The scanner of the module reports a measure: its progress, its content (the folder page, the policies), or why it failed."""
    from app.services import scans

    scans.record_module_state(db, payload.storage_root_id, status=payload.status, stats=payload.stats, method=payload.method,
                              elapsed_ms=payload.elapsed_ms, files=payload.files, progress=payload.progress, error=payload.error)
    if payload.status == "done":
        try:
            from app.services.policies import run_all

            run_all(db, only_root_ids={int(payload.storage_root_id)}, trigger="folder_scan", allow_jobs=False)
        except Exception:
            db.rollback()
    return ui_data({"stored": True})


class DelegatePayload(BaseModel):
    storage_root_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=300)


@router.post("/delegate-measure")
async def delegate_measure(payload: DelegatePayload, db: Session = Depends(get_db)):
    """The server cannot be walked on by the module (DFS, no WinRM): the worker of the core measures it through SMB;
    its result goes back to the module as any measure of the core."""
    from app.services import scans
    from app.services.probe_service import submit_probe_run

    job = await submit_probe_run({"kind": "folder", "protocol": "measure", "scope": "read", "target": {"storage_root_id": payload.storage_root_id},
                                  "context": {"storage_root_id": payload.storage_root_id, "ui_origin": "fives_delegate"}})
    scans.mark_requested(db, payload.storage_root_id, int(job.get("job_id") or 0) or None)
    return ui_data({"job_id": job.get("job_id"), "reason": payload.reason})
