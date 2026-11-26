"""History of the data indicators (Insights & Recommendations › Overview › Trends).

One snapshot a day of the platform and of each zone, taken during the health check (the first one of the day):
folders, coverage, volume, cold data, duplicates, secrets, full quotas, alerts, exposure of the ACLs, state of the
servers. The folders are counted with the rules of the express search of Storage Roots (folder_query.STATES): a point
of a curve is what the list showed that day. Kept 400 days. The history starts with the first snapshot: nothing is
reconstructed for the days before.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import folder_query
from app.services.storage_root_permissions import _json

KEEP_DAYS = 400
EXPOSURE_LEVELS = ("governed", "open_read", "open_write", "outside", "unknown")
SERVER_STATES = ("available", "degraded", "unavailable", "unknown")


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _count(rows: list[dict[str, Any]], state: str) -> int:
    rule = folder_query.STATES[state]
    return sum(1 for row in rows if rule(row))


def indicators(rows: list[dict[str, Any]], exposure: dict[str, int] | None = None, servers: dict[str, int] | None = None) -> dict[str, Any]:
    """The figures of one scope (the platform or a zone) from its folders, the exposure levels of their last ACL read
    and the states of its servers. Pure: tested without a database."""
    return {
        "folders": len(rows),
        "measured": len(rows) - _count(rows, "non-mesure"),
        "with_guardian": len(rows) - _count(rows, "sans-gardien"),
        "volume_bytes": int(sum(_num(row.get("content_size_bytes") if row.get("content_size_bytes") is not None else row.get("estimated_size_bytes")) for row in rows)),
        "cold_bytes": int(sum(_num(row.get("cold_1y_bytes")) for row in rows)),
        "dup_bytes": int(sum(_num(row.get("dup_wasted_bytes")) + _num(row.get("shared_dup_bytes")) for row in rows)),
        "secret_folders": _count(rows, "secret"),
        "quota_full": _count(rows, "quota-plein"),
        "alert_folders": _count(rows, "alerte"),
        "open_alerts": int(sum(_num(row.get("open_alerts_count")) for row in rows)),
        "exposure": {level: int((exposure or {}).get(level, 0)) for level in EXPOSURE_LEVELS} if exposure is not None else None,
        "servers": {state: int((servers or {}).get(state, 0)) for state in SERVER_STATES} if servers is not None else None,
    }


def _exposure_by_zone(db: Session) -> tuple[dict[str, int], dict[int, dict[str, int]]]:
    from app.services.exposure import build_exposure

    data = build_exposure(db, None)
    zones: dict[int, dict[str, int]] = {}
    for zone in data.get("zones") or []:
        counts = zones.setdefault(int(zone["zone_id"]), {level: 0 for level in EXPOSURE_LEVELS})
        for server in zone.get("servers") or []:
            for share in server.get("shares") or []:
                for folder in share.get("folders") or []:
                    counts[str(folder.get("level") or "unknown")] = counts.get(str(folder.get("level") or "unknown"), 0) + 1
    summary = data.get("summary") or {}
    return {level: int(summary.get(level, 0)) for level in EXPOSURE_LEVELS}, zones


def _servers_by_zone(db: Session) -> tuple[dict[str, int], dict[int, dict[str, int]]]:
    from app.services.storage_topology import StorageTopology

    overview = StorageTopology(db).overview()
    zones = {int(zone["id"]): {state: int(zone["states"].get(state, 0)) for state in SERVER_STATES} for zone in overview["zones"]}
    return {state: int(overview["summary"]["states"].get(state, 0)) for state in SERVER_STATES}, zones


def snapshot_rows(rows: list[dict[str, Any]], exposure: tuple[dict[str, int], dict[int, dict[str, int]]] | None,
                  servers: tuple[dict[str, int], dict[int, dict[str, int]]] | None) -> list[tuple[str, int, dict[str, Any]]]:
    """(scope type, scope id, indicators) of the platform and of each zone. Pure."""
    by_zone: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("zone_id"):
            by_zone.setdefault(int(row["zone_id"]), []).append(row)
    zone_ids = set(by_zone) | set((servers or ({}, {}))[1])
    out = [("platform", 0, indicators(rows, exposure[0] if exposure else None, servers[0] if servers else None))]
    for zone_id in sorted(zone_ids):
        out.append(("zone", zone_id, indicators(by_zone.get(zone_id, []),
                                                (exposure[1].get(zone_id, {}) if exposure else None),
                                                (servers[1].get(zone_id, {}) if servers else None))))
    return out


def take_snapshot(db: Session, today: date | None = None) -> int:
    """Today's snapshot, once a day (the first health check of the day); the older than KEEP_DAYS go. Returns the
    number of scopes written (0: already taken today)."""
    day = today or datetime.now(timezone.utc).date()
    taken = db.execute(
        text("SELECT 1 FROM data_indicator_history WHERE scope_type = 'platform' AND scope_id = 0 AND taken_on = :day"), {"day": day}
    ).first()
    if taken:
        return 0
    from app.services.policies import folder_rows

    rows = folder_rows(db)
    # Each part on its own: a failing one leaves its figures out (None), never the whole day
    try:
        exposure = _exposure_by_zone(db)
    except Exception:
        db.rollback()
        exposure = None
    try:
        servers = _servers_by_zone(db)
    except Exception:
        db.rollback()
        servers = None
    scopes = snapshot_rows(rows, exposure, servers)
    db.execute(
        text("""INSERT IGNORE INTO data_indicator_history (taken_on, scope_type, scope_id, indicators)
                VALUES (:day, :scope_type, :scope_id, :indicators)"""),
        [{"day": day, "scope_type": kind, "scope_id": scope_id, "indicators": json.dumps(values)} for kind, scope_id, values in scopes],
    )
    db.execute(text("DELETE FROM data_indicator_history WHERE taken_on < :limit"), {"limit": day - timedelta(days=KEEP_DAYS)})
    db.commit()
    return len(scopes)


def history(db: Session, *, days: int = 90, zone_id: int | None = None) -> list[dict[str, Any]]:
    """The snapshots of the platform (or of one zone) over the last days, oldest first."""
    since = datetime.now(timezone.utc).date() - timedelta(days=max(1, min(int(days), KEEP_DAYS)))
    rows = db.execute(
        text("""SELECT taken_on, indicators FROM data_indicator_history
                WHERE scope_type = :kind AND scope_id = :scope AND taken_on >= :since ORDER BY taken_on"""),
        {"kind": "zone" if zone_id else "platform", "scope": int(zone_id or 0), "since": since},
    ).mappings().all()
    return [{"day": str(row["taken_on"]), **(_json(row["indicators"]))} for row in rows]

