"""fives-service: the optional 5S and data hygiene module of BornToShare.

Reached through the BFF under /api/modules/fives/* (only while the module is licensed and switched on), with the
identity of the person and the shared internal token. Its data live in its own databases (b2s_fives,
b2s_fives_inventory); what it knows of the folders comes from the core (internal API), never from its database.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from app import core_client
from app.auth import Actor, actor, check_internal_token
from app.db import InventorySession, SessionLocal, create_schema
from app.services import duplicates, five_s, growth, reports

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [FIVES] %(name)s - %(message)s")
logger = logging.getLogger("fives")
app = FastAPI(title="BornToShare 5S module", docs_url=None, redoc_url=None, openapi_url=None)
_schema_ready = False


@app.on_event("startup")
def _startup() -> None:
    global _schema_ready
    for attempt in range(10):
        try:
            create_schema()
            _schema_ready = True
            return
        except Exception:
            logger.warning("Module databases not reachable yet (attempt %s)", attempt + 1, exc_info=attempt == 9)
            time.sleep(3)


@app.get("/health")
def health():
    return {"status": "ok" if _schema_ready else "degraded", "service": "fives-service", "schema": _schema_ready}


def _data(value: Any) -> dict[str, Any]:
    return {"data": value}


def _licensed(who: Actor = Depends(actor)) -> Actor:
    core_client.require_license()
    return who


def _rows(who: Actor, *, zone_id: int | None = None, root_id: int | None = None) -> list[dict[str, Any]]:
    """The folders of the person, with what the module adds: duplicates between folders, growth."""
    rows = core_client.folders(who, zone_id=zone_id, root_id=root_id)
    ids = [int(row.get("storage_root_id") or 0) for row in rows]
    with InventorySession() as inventory:
        shared = duplicates.shared(inventory, ids)
    with SessionLocal() as db:
        trends = growth.trends(db, ids)
    for row in rows:
        root_id_ = int(row.get("storage_root_id") or 0)
        entry = shared.get(root_id_) or {}
        row["shared_dup_bytes"] = entry.get("bytes")
        row["shared_dup_folders"] = len(entry.get("with") or []) if entry else None
        trend = trends.get(root_id_) or {}
        row["growth_30d_bytes"] = trend.get("growth_30d_bytes")
        row["bytes_per_day"] = trend.get("bytes_per_day")
    return rows


def _zones(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    zones = sorted({(int(row.get("zone_id") or 0), str(row.get("zone_name") or "—")) for row in rows if row.get("zone_id")}, key=lambda z: z[1])
    return [{"id": zid, "name": name} for zid, name in zones]


@app.get("/five-s")
def get_five_s(zone_id: int | None = None, who: Actor = Depends(_licensed)):
    everything = _rows(who)
    rows = [row for row in everything if not zone_id or int(row.get("zone_id") or 0) == int(zone_id)]
    scope = "Tous les dossiers visibles" if not zone_id else f"Zone {next((r.get('zone_name') for r in rows if r.get('zone_name')), zone_id)}"
    result = five_s.compute(rows)
    ids = [int(row.get("storage_root_id") or 0) for row in rows]
    with InventorySession() as inventory:
        between = duplicates.total(inventory, ids)
    with_dups = sorted((row for row in rows if int(row.get("dup_wasted_bytes") or 0) or int(row.get("shared_dup_bytes") or 0)),
                       key=lambda row: -(int(row.get("dup_wasted_bytes") or 0) + int(row.get("shared_dup_bytes") or 0)))
    result["duplicates"] = {
        "inside_bytes": sum(int(row.get("dup_wasted_bytes") or 0) for row in rows), "between_bytes": between["bytes"],
        "folders_count": len(with_dups), "measured_on_server": sum(1 for row in rows if row.get("dup_wasted_bytes") is not None),
        "folders": [{"id": int(row["storage_root_id"]), "name": row.get("storage_root_name"), "inside": int(row.get("dup_wasted_bytes") or 0),
                     "groups": int(row.get("dup_groups") or 0), "shared": int(row.get("shared_dup_bytes") or 0),
                     "with": int(row.get("shared_dup_folders") or 0)} for row in with_dups[:8]],
    }
    return _data({**result, "scope": scope, "zones": _zones(everything)})


def _one(who: Actor, root_id: int) -> dict[str, Any]:
    rows = core_client.folders(who, root_id=root_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    return rows[0]


@app.get("/storage-roots/{root_id}/growth")
def get_growth(root_id: int, who: Actor = Depends(_licensed)):
    """Measures of the last 180 days, the pace and the date the quota will be full."""
    row = _one(who, root_id)
    limit = row.get("quota_limit_bytes") if row.get("quota_status") == "applied" else None
    with SessionLocal() as db:
        return _data(growth.summary(db, int(root_id), limit))


@app.get("/storage-roots/{root_id}/duplicates")
def get_duplicates(root_id: int, who: Actor = Depends(_licensed)):
    """The files of the folder also present in other folders the person may see."""
    rows = core_client.folders(who)
    if not any(int(row.get("storage_root_id") or 0) == int(root_id) for row in rows):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    with InventorySession() as inventory:
        shared = duplicates.shared(inventory, [int(row.get("storage_root_id") or 0) for row in rows]).get(int(root_id))
    names = {int(row.get("storage_root_id") or 0): row.get("storage_root_name") for row in rows}
    if shared:
        shared["with_names"] = [names.get(other) or str(other) for other in shared["with"]]
    return _data({"shared": shared})


@app.get("/reports")
def list_reports(who: Actor = Depends(_licensed)):
    return _data([{"key": key, "title": title, "description": description, "source": "fives"} for key, (title, description) in reports.KINDS.items()])


@app.get("/reports/{kind}")
def get_report(kind: str, zone_id: int | None = None, who: Actor = Depends(_licensed)):
    if kind not in reports.KINDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    everything = _rows(who)
    rows = [row for row in everything if not zone_id or int(row.get("zone_id") or 0) == int(zone_id)]
    scope = "Tous les dossiers visibles" if not zone_id else f"Zone {next((r.get('zone_name') for r in rows if r.get('zone_name')), zone_id)}"
    with InventorySession() as inventory:
        between = duplicates.total(inventory, [int(row.get("storage_root_id") or 0) for row in rows])
    return _data({**reports.build(kind, rows, scope, between), "zones": _zones(everything)})


class MeasurePayload(BaseModel):
    storage_root_id: int = Field(gt=0)
    measured_at: datetime | None = None
    bytes: int = Field(ge=0)
    stats: dict[str, Any] = Field(default_factory=dict)
    fingerprints: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


@app.post("/internal/measures", status_code=status.HTTP_202_ACCEPTED)
def receive_measure(payload: MeasurePayload, request: Request):
    """A measure of a folder, sent by the core: one more point of its history, and the fingerprints of its biggest files."""
    check_internal_token(request)
    when = (payload.measured_at or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(tzinfo=None)
    _retry(lambda: _store_point(payload, when))
    kept = _retry(lambda: _store_prints(payload))
    return _data({"stored": True, "fingerprints": kept})


def _store_point(payload: MeasurePayload, when: datetime) -> None:
    with SessionLocal() as db:
        growth.record(db, payload.storage_root_id, measured_at=when, bytes_=payload.bytes, stats=payload.stats)
        db.commit()


def _store_prints(payload: MeasurePayload) -> int:
    with InventorySession() as inventory:
        kept = duplicates.replace(inventory, payload.storage_root_id, payload.fingerprints)
        inventory.commit()
    return kept


def _retry(work):
    """Many measures land at once: a transaction picked as a deadlock victim is tried again."""
    from sqlalchemy.exc import OperationalError

    for attempt in range(3):
        try:
            return work()
        except OperationalError:
            if attempt == 2:
                raise
            time.sleep(0.2 * (attempt + 1))
