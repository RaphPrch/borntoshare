"""The queue of the scanner of the module (scan_runs), its settings, and the schedule.

A scan is asked by a person (« Measure »), by a policy, or by the schedule (every folder every `interval_days`,
inside the window). The scanner (fives-scanner, one or more instances) takes the oldest runnable scan:
- at most `per_server` scans at a time on the same file server;
- the scheduled ones only inside the window (e.g. 20:00 → 06:00); the ones asked by a person at once;
- a scan whose scanner stopped answering (no heartbeat for 10 minutes) goes back to the queue and resumes.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

DEFAULTS: dict[str, Any] = {
    "schedule_enabled": True,
    "window_start": "20:00",
    "window_end": "06:00",
    "timezone": "Europe/Paris",
    "per_server": 1,
    "interval_days": 7,
    "full_every_days": 30,
    "hash_files_max": 20000,
}
ACTIVE = ("queued", "running")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: Any) -> str | None:
    return value.isoformat() + "Z" if value else None


def host_of(root_path: str | None) -> str:
    parts = [part for part in str(root_path or "").replace("/", "\\").split("\\") if part]
    return parts[0].lower() if parts else "?"


def get_settings(db: Session) -> dict[str, Any]:
    row = db.execute(text("SELECT value_json FROM module_settings WHERE setting_key = 'scanner'")).first()
    stored = json.loads(row[0]) if row and row[0] else {}
    return {**DEFAULTS, **{key: value for key, value in stored.items() if key in DEFAULTS}}


def save_settings(db: Session, values: dict[str, Any], by: str | None) -> dict[str, Any]:
    merged = {**get_settings(db), **{key: value for key, value in values.items() if key in DEFAULTS}}
    db.execute(
        text("""INSERT INTO module_settings (setting_key, value_json, updated_by) VALUES ('scanner', :v, :by)
                ON DUPLICATE KEY UPDATE value_json = VALUES(value_json), updated_by = VALUES(updated_by)"""),
        {"v": json.dumps(merged), "by": by},
    )
    db.commit()
    return merged


def in_window(settings: dict[str, Any], now_utc: datetime | None = None) -> bool:
    """Inside the window of the schedule (a window may go over midnight: 20:00 → 06:00)."""
    local = (now_utc or _now()).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(str(settings.get("timezone") or "Europe/Paris")))
    start = time.fromisoformat(str(settings["window_start"]))
    end = time.fromisoformat(str(settings["window_end"]))
    current = local.time().replace(second=0, microsecond=0)
    return start <= current < end if start < end else (current >= start or current < end)


def enqueue(db: Session, folders: list[dict[str, Any]], *, reason: str, by: str | None) -> list[int]:
    """Queue a scan of each folder that has none queued or running. Returns the folders queued."""
    ids = [int(row["storage_root_id"]) for row in folders]
    if not ids:
        return []
    busy = {int(row[0]) for row in db.execute(
        text("SELECT storage_root_id FROM scan_runs WHERE status IN ('queued', 'running') AND storage_root_id IN :ids")
        .bindparams(bindparam("ids", expanding=True)), {"ids": ids}).all()}
    queued = []
    for row in folders:
        root_id = int(row["storage_root_id"])
        if root_id in busy:
            continue
        db.execute(text("INSERT INTO scan_runs (storage_root_id, host, reason, requested_by) VALUES (:id, :host, :reason, :by)"),
                   {"id": root_id, "host": host_of(row.get("root_path")), "reason": reason, "by": by})
        queued.append(root_id)
    db.commit()
    return queued


def _run(row: Any) -> dict[str, Any]:
    load = lambda value: json.loads(value) if value else None  # noqa: E731
    return {"id": int(row["id"]), "storage_root_id": int(row["storage_root_id"]), "host": row["host"], "status": row["status"], "reason": row["reason"],
            "mode": row["mode"], "requested_by": row["requested_by"], "requested_at": _iso(row["requested_at"]), "started_at": _iso(row["started_at"]),
            "heartbeat_at": _iso(row["heartbeat_at"]), "finished_at": _iso(row["finished_at"]), "scanner_id": row["scanner_id"],
            "attempts": int(row["attempts"] or 0), "progress": load(row["progress_json"]), "summary": load(row["summary_json"]), "error": row["error_message"]}


def overview(db: Session, storage_root_ids: list[int]) -> dict[str, Any]:
    """The queue and the last scans of these folders, and the scanners seen lately."""
    ids = sorted({int(value) for value in storage_root_ids}) or [0]
    rows = db.execute(
        text("""SELECT * FROM scan_runs WHERE storage_root_id IN :ids AND (status IN ('queued', 'running') OR requested_at >= :since)
                ORDER BY FIELD(status, 'running', 'queued') DESC, requested_at DESC LIMIT 300""").bindparams(bindparam("ids", expanding=True)),
        {"ids": ids, "since": _now() - timedelta(days=7)},
    ).mappings().all()
    runs = [_run(row) for row in rows]
    scanners = [{"id": row[0], "last_seen": _iso(row[1])} for row in db.execute(
        text("SELECT scanner_id, MAX(heartbeat_at) FROM scan_runs WHERE scanner_id IS NOT NULL AND heartbeat_at >= :since GROUP BY scanner_id"),
        {"since": _now() - timedelta(hours=24)}).all()]
    counts = {status: sum(1 for run in runs if run["status"] == status) for status in ("queued", "running", "done", "failed", "delegated")}
    return {"runs": runs, "counts": counts, "scanners": scanners}


def cancel(db: Session, run_id: int) -> bool:
    result = db.execute(text("UPDATE scan_runs SET status = 'cancelled', finished_at = :now WHERE id = :id AND status = 'queued'"),
                        {"id": int(run_id), "now": _now()})
    db.commit()
    return bool(result.rowcount)


def due(db: Session, folders: list[dict[str, Any]], settings: dict[str, Any], limit: int = 200) -> list[dict[str, Any]]:
    """The folders whose last scan is older than interval_days (or never scanned), oldest first."""
    ids = [int(row["storage_root_id"]) for row in folders]
    if not ids:
        return []
    last = {int(root): at for root, at in db.execute(
        text("SELECT storage_root_id, MAX(requested_at) FROM scan_runs WHERE storage_root_id IN :ids AND status <> 'cancelled' GROUP BY storage_root_id")
        .bindparams(bindparam("ids", expanding=True)), {"ids": ids}).all()}
    limit_at = _now() - timedelta(days=int(settings["interval_days"]))
    waiting = [row for row in folders if last.get(int(row["storage_root_id"])) is None or last[int(row["storage_root_id"])] < limit_at]
    return sorted(waiting, key=lambda row: last.get(int(row["storage_root_id"])) or datetime.min)[:limit]
