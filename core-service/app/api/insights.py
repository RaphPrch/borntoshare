"""The reports of the core: computed on the folders the person may see (administrators: all;
guardians and backup guardians: theirs), optionally in one zone."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import reports
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


@router.get("/reports")
def list_reports():
    # The 5S and data hygiene reports are served by the 5S module (fives-service)
    return ui_data([{"key": key, "title": title, "description": description, "source": "core"} for key, (title, description) in reports.KINDS.items()])


@router.get("/reports/{kind}")
def get_report(kind: str, request: Request, zone_id: int | None = None, db: Session = Depends(get_db)):
    if kind not in reports.KINDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    rows, scope, zones = _rows(db, request, zone_id)
    return ui_data({**reports.build(db, kind, rows, scope), "zones": zones})
