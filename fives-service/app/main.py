"""fives-service: the optional 5S and data hygiene module of BornToShare.

Reached through the BFF under /api/modules/fives/* (only while the module is licensed and switched on), with the
identity of the person and the shared internal token. Its data live in its own databases (b2s_fives,
b2s_fives_inventory); what it knows of the folders comes from the core (internal API), never from its database.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from app import core_client
from app.auth import Actor, actor, check_internal_token
from app.db import InventorySession, SessionLocal, check_schema
from app.services import duplicates, five_s, growth, reports, scans

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [FIVES] %(name)s - %(message)s")
logger = logging.getLogger("fives")
app = FastAPI(title="BornToShare 5S module", docs_url=None, redoc_url=None, openapi_url=None)
_schema_ready = False


@app.on_event("startup")
def _startup() -> None:
    global _schema_ready
    for attempt in range(10):
        try:
            check_schema()
            _schema_ready = True
            break
        except Exception:
            logger.warning("Module databases not reachable or not installed yet (attempt %s)", attempt + 1, exc_info=attempt == 9)
            time.sleep(3)
    threading.Thread(target=_schedule_loop, name="fives-schedule", daemon=True).start()


SYSTEM = Actor(identity_id=None, roles=frozenset({"platform_admin"}), display_name="Planificateur 5S")


def _schedule_tick() -> dict[str, Any]:
    """Each minute: scans stuck without heartbeat go back to the queue; inside the window, the folders due are queued."""
    from sqlalchemy import text as sql

    with SessionLocal() as db:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stale = now - timedelta(minutes=10)
        db.execute(sql("UPDATE scan_runs SET status = 'failed', finished_at = :now, error_message = 'The scanner stopped answering three times'"
                       " WHERE status = 'running' AND heartbeat_at < :stale AND attempts >= 3"), {"now": now, "stale": stale})
        requeued = db.execute(sql("UPDATE scan_runs SET status = 'queued', scanner_id = NULL WHERE status = 'running' AND heartbeat_at < :stale"),
                              {"stale": stale}).rowcount
        db.commit()
        if not core_client.license_state().get("enabled"):
            return {"requeued": requeued, "queued": 0}
        settings = scans.get_settings(db)
        if not settings["schedule_enabled"] or not scans.in_window(settings):
            return {"requeued": requeued, "queued": 0}
        folders = core_client.folders(SYSTEM)
        queued = scans.enqueue(db, scans.due(db, folders, settings), reason="schedule", by="Planificateur 5S")
        return {"requeued": requeued, "queued": len(queued)}


def _schedule_loop() -> None:
    while True:
        try:
            result = _schedule_tick()
            if result.get("queued") or result.get("requeued"):
                logger.info("Schedule: %s", result)
        except Exception:
            logger.warning("Schedule tick failed", exc_info=True)
        time.sleep(60)


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


# ---- scanner of the module: queue, settings ----

@app.get("/scans")
def get_scans(who: Actor = Depends(_licensed)):
    rows = core_client.folders(who)
    names = {int(row["storage_root_id"]): row.get("storage_root_name") for row in rows}
    with SessionLocal() as db:
        data = scans.overview(db, list(names))
        settings = scans.get_settings(db)
    for run in data["runs"]:
        run["folder_name"] = names.get(run["storage_root_id"])
    return _data({**data, "settings": settings, "in_window": scans.in_window(settings)})


class ScanRequest(BaseModel):
    root_ids: list[int] = Field(min_length=1, max_length=1000)


@app.post("/scans")
def request_scans(payload: ScanRequest, who: Actor = Depends(_licensed)):
    """Scan these folders now (a person asks: no window), among those the person may see."""
    rows = [row for row in core_client.folders(who) if int(row["storage_root_id"]) in set(payload.root_ids)]
    with SessionLocal() as db:
        queued = scans.enqueue(db, rows, reason="manual", by=who.display_name)
    return _data({"queued": queued, "skipped": sorted(set(payload.root_ids) - set(queued))})


@app.post("/scans/{run_id}/cancel")
def cancel_scan(run_id: int, who: Actor = Depends(_licensed)):
    if not who.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="platform_admin role required")
    with SessionLocal() as db:
        if not scans.cancel(db, run_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error_code": "SCAN_NOT_QUEUED", "message": "Only a scan waiting in the queue can be cancelled"})
    return _data({"cancelled": run_id})


class SettingsPayload(BaseModel):
    schedule_enabled: bool
    window_start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    window_end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    per_server: int = Field(ge=1, le=8)
    interval_days: int = Field(ge=1, le=90)
    full_every_days: int = Field(ge=1, le=365)
    hash_files_max: int = Field(ge=0, le=500000)


@app.get("/settings")
def get_settings_route(who: Actor = Depends(_licensed)):
    """The settings of the scanner (window, scans per server, frequency, full walk, fingerprints)."""
    with SessionLocal() as db:
        settings = scans.get_settings(db)
    return _data({**settings, "in_window": scans.in_window(settings)})


@app.put("/settings")
def put_settings(payload: SettingsPayload, who: Actor = Depends(_licensed)):
    if not who.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="platform_admin role required")
    with SessionLocal() as db:
        return _data(scans.save_settings(db, payload.model_dump(), who.display_name))


class InternalScanRequest(BaseModel):
    roots: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    reason: str = Field(default="manual", pattern="^(manual|policy|schedule)$")
    by: str | None = None


@app.post("/internal/scans")
def internal_scans(payload: InternalScanRequest, request: Request):
    """The core asks for scans (« Measure » in the folder page, a policy): the scanner of the module does them."""
    check_internal_token(request)
    with SessionLocal() as db:
        queued = scans.enqueue(db, payload.roots, reason=payload.reason, by=payload.by)
    return _data({"queued": queued})
