"""The reports of the core: computed on the folders the person may see (administrators: all;
guardians and backup guardians: theirs), optionally in one zone."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import features, reports
from app.services.authorization import actor_from_request, admin_only, filter_storage_root_rows, require_storage_roots_index

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
def list_reports(db: Session = Depends(get_db)):
    # The 5S and data hygiene reports are served by the 5S module (fives-service); a 5S-only installation has no
    # report of the access governance
    kinds = reports.kinds(features.enabled(db, "governance"))
    return ui_data([{"key": key, "title": title, "description": description, "source": "core"} for key, (title, description) in kinds.items()])


@router.get("/reports/{kind}")
def get_report(kind: str, request: Request, zone_id: int | None = None, db: Session = Depends(get_db)):
    governance = features.enabled(db, "governance")
    if kind not in reports.kinds(governance):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    rows, scope, zones = _rows(db, request, zone_id)
    return ui_data({**reports.build(db, kind, rows, scope, governance), "zones": zones})


@router.get("/history", dependencies=[Depends(admin_only)])
def get_history(days: int = Query(90, ge=1, le=400), zone_id: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    """One snapshot a day of the data indicators of the platform or of a zone (administrators: the figures of every
    folder), oldest first. Empty until the first snapshot (taken by the health check)."""
    from app.services.indicator_history import history

    return ui_data(history(db, days=days, zone_id=zone_id))
