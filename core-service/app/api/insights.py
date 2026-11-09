"""The 5S of the file shares and the reports: computed on the folders the person may see (administrators: all;
guardians and backup guardians: theirs), optionally in one zone."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import five_s, reports
from app.services.authorization import actor_from_request, filter_storage_root_rows, require_storage_roots_index

router = APIRouter(prefix="/insights", tags=["insights"])


def _rows(db: Session, request: Request, zone_id: int | None) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    from app.services.policies import folder_rows

    actor = actor_from_request(request)
    require_storage_roots_index(db, actor)
    rows = filter_storage_root_rows(db, actor, folder_rows(db))
    zones = sorted({(int(row.get("zone_id") or 0), str(row.get("zone_name") or "—")) for row in rows if row.get("zone_id")}, key=lambda z: z[1])
    scope = "Tous les dossiers visibles"
    if zone_id:
        rows = [row for row in rows if int(row.get("zone_id") or 0) == int(zone_id)]
        scope = f"Zone {next((row.get('zone_name') for row in rows if row.get('zone_name')), zone_id)}"
    return rows, scope, [{"id": zid, "name": name} for zid, name in zones]


@router.get("/five-s")
def get_five_s(request: Request, zone_id: int | None = None, db: Session = Depends(get_db)):
    rows, scope, zones = _rows(db, request, zone_id)
    from app.services.scans import cross_duplicate_total

    ids = [int(row.get("storage_root_id") or 0) for row in rows]
    result = five_s.compute(rows, five_s.scanned_at_by_root(db, ids))
    # Duplicates: inside each folder (found on the server) and between folders (same fingerprint)
    with_dups = sorted((row for row in rows if int(row.get("dup_wasted_bytes") or 0) or int(row.get("shared_dup_bytes") or 0)),
                       key=lambda row: -(int(row.get("dup_wasted_bytes") or 0) + int(row.get("shared_dup_bytes") or 0)))
    duplicates = {
        "inside_bytes": sum(int(row.get("dup_wasted_bytes") or 0) for row in rows),
        "between_bytes": cross_duplicate_total(db, ids)["bytes"],
        "folders_count": len(with_dups),
        "measured_on_server": sum(1 for row in rows if row.get("dup_wasted_bytes") is not None),
        "folders": [{"id": int(row["storage_root_id"]), "name": row.get("storage_root_name"), "inside": int(row.get("dup_wasted_bytes") or 0),
                     "groups": int(row.get("dup_groups") or 0), "shared": int(row.get("shared_dup_bytes") or 0),
                     "with": int(row.get("shared_dup_folders") or 0)} for row in with_dups[:8]],
    }
    return ui_data({**result, "scope": scope, "zones": zones, "duplicates": duplicates})


@router.get("/reports")
def list_reports():
    return ui_data([{"key": key, "title": title, "description": description} for key, (title, description) in reports.KINDS.items()])


@router.get("/reports/{kind}")
def get_report(kind: str, request: Request, zone_id: int | None = None, db: Session = Depends(get_db)):
    if kind not in reports.KINDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    rows, scope, zones = _rows(db, request, zone_id)
    return ui_data({**reports.build(db, kind, rows, scope), "zones": zones})
