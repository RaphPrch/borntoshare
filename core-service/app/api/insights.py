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


def _rows(db: Session, request: Request, zone_id: int | None, server_id: int | None = None, tag: str | None = None,
          q: str | None = None) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """The folders the person may see, narrowed by the filters of the report (zone, server, tag, express search: the
    same « est:… tag:… » as Storage Roots), and the values each filter offers."""
    from app.services import folder_query
    from app.services.policies import folder_rows

    actor = actor_from_request(request)
    require_storage_roots_index(db, actor)
    rows = filter_storage_root_rows(db, actor, folder_rows(db))
    zones = sorted({(int(row.get("zone_id") or 0), str(row.get("zone_name") or "—")) for row in rows if row.get("zone_id")}, key=lambda z: z[1])
    servers = sorted({(int(row.get("storage_endpoint_id") or 0), str(row.get("storage_endpoint_name") or "—")) for row in rows
                      if row.get("storage_endpoint_id") and (not zone_id or int(row.get("zone_id") or 0) == int(zone_id))}, key=lambda s: s[1])
    tags = sorted({name for row in rows for name in folder_query.tag_names(row)}, key=str.lower)
    scope = ["Tous les dossiers visibles"]
    if zone_id:
        rows = [row for row in rows if int(row.get("zone_id") or 0) == int(zone_id)]
        scope = [f"Zone {next((row.get('zone_name') for row in rows if row.get('zone_name')), zone_id)}"]
    if server_id:
        rows = [row for row in rows if int(row.get("storage_endpoint_id") or 0) == int(server_id)]
        scope.append(f"serveur {next((row.get('storage_endpoint_name') for row in rows if row.get('storage_endpoint_name')), server_id)}")
    if tag:
        rows = [row for row in rows if any(folder_query.fold(name) == folder_query.fold(tag) for name in folder_query.tag_names(row))]
        scope.append(f"tag {tag}")
    if q and q.strip():
        unknown = folder_query.unknown_states(q)
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown state: {', '.join(unknown)}")
        rows = [row for row in rows if folder_query.matches(row, q)]
        scope.append(f"recherche « {q.strip()} »")
    options = {"zones": [{"id": zid, "name": name} for zid, name in zones], "servers": [{"id": sid, "name": name} for sid, name in servers],
               "tags": tags}
    return rows, " · ".join(scope), options


@router.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    # The reports this installation serves (their license on); the 5S and data hygiene reports come from the 5S module
    kinds = reports.kinds(features.enabled(db, "governance"), features.enabled(db, "fives"))
    return ui_data([{"key": key, "title": title, "description": description, "license": license_, "source": "core"}
                    for key, (title, description, license_) in kinds.items()])


@router.get("/reports/{kind}")
def get_report(
    kind: str,
    request: Request,
    zone_id: int | None = None,
    server_id: int | None = None,
    tag: str | None = Query(None, max_length=128),
    q: str | None = Query(None, max_length=300),
    days: int = Query(30, ge=1, le=400),
    db: Session = Depends(get_db),
):
    governance = features.enabled(db, "governance")
    fives = features.enabled(db, "fives")
    if kind not in reports.kinds(governance, fives):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    rows, scope, options = _rows(db, request, zone_id, server_id, tag, q)
    from app.services.storage_topology import StorageTopology

    body = reports.build(db, kind, rows, scope, governance, fives, days=days, stale_before=StorageTopology(db).stale_before)
    return ui_data({**body, **options})


@router.get("/history", dependencies=[Depends(admin_only)])
def get_history(days: int = Query(90, ge=1, le=400), zone_id: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    """One snapshot a day of the data indicators of the platform or of a zone (administrators: the figures of every
    folder), oldest first. Empty until the first snapshot (taken by the health check)."""
    from app.services.indicator_history import history

    return ui_data(history(db, days=days, zone_id=zone_id))
