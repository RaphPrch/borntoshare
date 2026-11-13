"""Measure of the governed folders, a job of its own (folder_scan, scan queue), apart from their test (pack 156).

What a measure brings back is kept where the folder page already reads its content (discovered_permissions_json:
content_size_bytes, content_stats), one more point of its history, and the fingerprints of its biggest files.
Duplicates inside a folder are found by the server itself (content_stats.duplicates); the history of the measures
and the duplicates between folders belong to the 5S module, which receives each measure (app.services.modules).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

logger = logging.getLogger("core.scans")
ACTION = "folder_scan"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: Any) -> str | None:
    return value.isoformat() + "Z" if value else None


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None) if value else None
    except ValueError:
        return None


def mark_requested(db: Session, storage_root_id: int, job_id: int | None) -> None:
    db.execute(
        text(
            """
            INSERT INTO storage_root_scans (storage_root_id, status, job_id, requested_at, error_message)
            VALUES (:id, 'running', :job, :now, NULL)
            ON DUPLICATE KEY UPDATE status = 'running', job_id = VALUES(job_id), requested_at = VALUES(requested_at), error_message = NULL
            """
        ),
        {"id": int(storage_root_id), "job": job_id, "now": _now()},
    )
    db.commit()


def get(db: Session, storage_root_id: int) -> dict[str, Any] | None:
    row = db.execute(text("SELECT * FROM storage_root_scans WHERE storage_root_id = :id"), {"id": int(storage_root_id)}).mappings().first()
    if not row:
        return None
    import json

    progress = row.get("progress_json")
    return {"status": row["status"], "job_id": row["job_id"], "method": row["method"], "fallback_reason": row["fallback_reason"],
            "requested_at": _iso(row["requested_at"]), "finished_at": _iso(row["finished_at"]), "elapsed_ms": row["elapsed_ms"],
            "files": row["files"], "error": row["error_message"], "mode": row.get("mode"),
            "progress": json.loads(progress) if progress else None}


def record_result(db: Session, storage_root_id: int, job_id: int | None, result_json: dict | None) -> bool:
    from app.data.models.storage_root import StorageRoot
    from app.services import modules

    details = (result_json or {}).get("details") if isinstance(result_json, dict) else None
    stats = details.get("content_stats") if isinstance(details, dict) else None
    if not isinstance(stats, dict):
        return False
    root = db.get(StorageRoot, int(storage_root_id))
    if root is None:
        return False
    now = _now()
    current = dict(root.discovered_permissions_json) if isinstance(root.discovered_permissions_json, dict) else {}
    # Never a good measure replaced by an empty one: kept, the measure fails and the folder is flagged
    if emptied(current, stats):
        problem = "La mesure n'a trouvé aucun fichier alors que le dossier en contenait : dernière mesure conservée"
        record_failure(db, int(storage_root_id), job_id, problem)
        unreadable_alert(db, int(storage_root_id), problem)
        return False
    # A new dict: the JSON column is seen as changed (the ACL part of the last test stays as it is)
    root.discovered_permissions_json = {**current, "content_previous": with_previous(current), "content_size_bytes": int(stats.get("bytes") or 0),
                                        "content_updated_at": now.isoformat() + "+00:00", "content_stats": stats,
                                        "content_scan_job_id": job_id, "content_interim": False}
    db.execute(
        text(
            """
            UPDATE storage_root_scans SET status = 'done', job_id = :job, method = :method, fallback_reason = :fallback,
              finished_at = :now, elapsed_ms = :elapsed, files = :files, error_message = NULL WHERE storage_root_id = :id
            """
        ),
        {"id": int(storage_root_id), "job": job_id, "method": str(stats.get("method") or "")[:16] or None,
         "fallback": (str(details.get("fallback_reason") or "")[:300] or None), "now": now, "elapsed": stats.get("elapsed_ms"),
         "files": stats.get("files")},
    )
    db.commit()
    # History, growth and duplicates between folders: the 5S module (its own databases), when it is on
    modules.push_measure(db, int(storage_root_id), measured_at=now, bytes_=int(stats.get("bytes") or 0), stats=stats,
                         fingerprints=list(details.get("fingerprints") or []))
    tell_end(db, int(storage_root_id), ok=True, stats=stats)
    return True


def record_failure(db: Session, storage_root_id: int, job_id: int | None, message: str | None) -> None:
    db.execute(
        text("UPDATE storage_root_scans SET status = 'failed', job_id = :job, finished_at = :now, error_message = :message WHERE storage_root_id = :id"),
        {"id": int(storage_root_id), "job": job_id, "now": _now(), "message": (message or "")[:600]},
    )
    db.commit()
    tell_end(db, int(storage_root_id), ok=False, problem=message)


def tell_end(db: Session, storage_root_id: int, *, ok: bool, stats: dict | None = None, problem: str | None = None) -> None:
    """The person who asked for this measure is told in the bell (nobody for a scheduled one)."""
    from app.services import inbox

    if ok and isinstance(stats, dict):
        files, size = int(stats.get("files") or 0), int(stats.get("bytes") or 0)
        detail = f"{files:,} fichier(s) · {size / 1024 ** 3:,.1f} Go".replace(",", " ")
    else:
        detail = (problem or "")[:300] or None
    inbox.tell_requester(db, "measure", storage_root_id, ok=ok, detail=detail)


def states_by_root(db: Session, storage_root_ids: list[int]) -> dict[int, str]:
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {}
    try:
        rows = db.execute(text("SELECT storage_root_id, status FROM storage_root_scans WHERE storage_root_id IN :ids")
                          .bindparams(bindparam("ids", expanding=True)), {"ids": ids}).all()
    except Exception:
        db.rollback()
        return {}
    return {int(root_id): str(state) for root_id, state in rows}




def record_module_state(db: Session, storage_root_id: int, *, status: str, stats: dict | None = None, method: str | None = None,
                        elapsed_ms: int | None = None, files: int | None = None, progress: dict | None = None,
                        error: str | None = None, interim: bool = False) -> tuple[str, str | None]:
    """What the scanner of the 5S module reports: running (with its progress), done (with the content), failed.
    interim: running with the figures of the walk, before the fingerprints; they replace the shown content but never
    enter the kept previous measures (the final « done » takes their place).
    Returns the state kept and its problem (a measure that comes back empty is kept as a failure)."""
    import json

    from app.data.models.storage_root import StorageRoot

    now = _now()
    if (status == "done" or (status == "running" and interim)) and isinstance(stats, dict):
        root = db.get(StorageRoot, int(storage_root_id))
        current = dict(root.discovered_permissions_json) if root is not None and isinstance(root.discovered_permissions_json, dict) else {}
        if root is not None and emptied(current, stats):
            if status == "done":
                status, stats = "failed", None
                error = "La mesure n'a trouvé aucun fichier alors que le dossier en contenait : dernière mesure conservée"
        elif root is not None:
            # An interim content never becomes a previous measure: the one shown before it stays the last kept
            previous = (current.get("content_previous") or []) if current.get("content_interim") else with_previous(current)
            root.discovered_permissions_json = {**current, "content_previous": previous, "content_size_bytes": int(stats.get("bytes") or 0),
                                                "content_updated_at": now.isoformat() + "+00:00", "content_stats": stats,
                                                "content_interim": status == "running"}
    db.execute(
        text(
            """
            INSERT INTO storage_root_scans (storage_root_id, status, method, requested_at, finished_at, elapsed_ms, files, error_message, progress_json, mode)
            VALUES (:id, :status, :method, :now, :finished, :elapsed, :files, :error, :progress, :mode)
            ON DUPLICATE KEY UPDATE status = VALUES(status), method = COALESCE(VALUES(method), method),
              finished_at = VALUES(finished_at), elapsed_ms = COALESCE(VALUES(elapsed_ms), elapsed_ms), files = COALESCE(VALUES(files), files),
              error_message = VALUES(error_message), progress_json = VALUES(progress_json), mode = COALESCE(VALUES(mode), mode),
              fallback_reason = IF(VALUES(status) = 'running', fallback_reason, NULL)
            """
        ),
        {"id": int(storage_root_id), "status": status, "method": method or ("module" if status == "running" else None), "now": now,
         "finished": now if status in {"done", "failed"} else None, "elapsed": elapsed_ms, "files": files, "error": (error or None) and error[:600],
         "progress": json.dumps(progress) if progress else None, "mode": (progress or {}).get("mode") or (stats or {}).get("mode")},
    )
    db.commit()
    return status, error


async def request_measure(db: Session, storage_root_id: int, *, reason: str = "manual", by: str | None = None) -> int | None:
    """Measure a folder: by the scanner of the 5S module when it is on (incremental, on the server), else by the
    worker of the core. Returns the job id of the core (None when the module does it)."""
    from app.services import features, modules
    from app.services.probe_service import submit_probe_run

    if features.enabled(db, "fives") and modules.request_scan(db, storage_root_id, reason=reason, by=by):
        mark_requested(db, storage_root_id, None)
        db.execute(text("UPDATE storage_root_scans SET method = 'module', progress_json = NULL WHERE storage_root_id = :id"), {"id": int(storage_root_id)})
        db.commit()
        return None
    job = await submit_probe_run({
        "kind": "folder", "protocol": "measure", "scope": "read",
        "target": {"storage_root_id": int(storage_root_id)},
        "context": {"storage_root_id": int(storage_root_id), "ui_origin": f"folder_measure_{reason}"},
    })
    job_id = int(job.get("job_id") or 0) or None
    mark_requested(db, storage_root_id, job_id)
    return job_id


def unreadable_alert(db: Session, root_id: int, problem: str | None) -> None:
    """A folder the scanner could not read (disk error, folder gone, pieces unreadable) raises an alert; the next clean
    measure resolves it. Without it, a broken disk stays silent and its figures quietly go wrong."""
    from datetime import datetime, timezone

    from sqlalchemy import text as _text

    from app.data.repositories.governance_alerts_repo import GovernanceAlertsRepo

    key = f"fives_unreadable:{int(root_id)}"
    try:
        if not problem:
            db.execute(_text("UPDATE governance_alerts SET status = 'resolved', resolved_at = :now WHERE alert_key = :key AND status <> 'resolved'"),
                       {"now": datetime.now(timezone.utc).replace(tzinfo=None), "key": key})
            db.commit()
            return
        row = db.execute(_text("""SELECT r.name, r.storage_endpoint_id, e.zone_id FROM storage_roots r LEFT JOIN storage_endpoints e ON e.id = r.storage_endpoint_id
                                  WHERE r.id = :id"""), {"id": int(root_id)}).mappings().first() or {}
        GovernanceAlertsRepo(db)._upsert_alert({
            "alert_key": key, "scope_type": "storage_root", "scope_id": int(root_id), "alert_type": "fives_unreadable",
            "severity": "warning", "title": "Dossier en partie illisible pour le scanner 5S",
            "message": f"{problem[:400]} — vérifiez le disque ou le partage, puis mesurez à nouveau.",
            "source_type": "fives", "source_id": str(int(root_id)), "zone_id": row.get("zone_id"),
            "storage_endpoint_id": row.get("storage_endpoint_id"), "storage_root_id": int(root_id),
            "metadata_json": {"problem": problem[:500], "storage_root_name": row.get("name")},
        })
        db.commit()
    except Exception:
        db.rollback()


def emptied(current: dict, stats: dict) -> bool:
    """A measure that finds no file in a folder that held some: the folder was not read (disk gone, share moved…)
    far more often than it was emptied. Its figures must not replace the good ones."""
    before = int(((current or {}).get("content_stats") or {}).get("files") or 0)
    return before > 0 and int((stats or {}).get("files") or 0) == 0



# Measures kept per folder besides the current one: a bad one can be undone, two can be compared
KEEP_PREVIOUS = 3


def with_previous(current: dict) -> list[dict]:
    """The history once the current measure becomes the previous one (newest first, at most KEEP_PREVIOUS)."""
    history = [item for item in (current or {}).get("content_previous") or [] if isinstance(item, dict)]
    if (current or {}).get("content_stats"):
        history.insert(0, {"at": current.get("content_updated_at"), "bytes": current.get("content_size_bytes"), "stats": current["content_stats"]})
    return history[:KEEP_PREVIOUS]


def restore_previous(db: Session, storage_root_id: int, index: int) -> bool:
    """Back to a previous measure (the current one takes its place in the history)."""
    from app.data.models.storage_root import StorageRoot

    root = db.get(StorageRoot, int(storage_root_id))
    current = dict(root.discovered_permissions_json) if root is not None and isinstance(root.discovered_permissions_json, dict) else {}
    history = [item for item in current.get("content_previous") or [] if isinstance(item, dict)]
    if root is None or not 0 <= int(index) < len(history):
        return False
    chosen = history.pop(int(index))
    if current.get("content_stats"):
        history.insert(0, {"at": current.get("content_updated_at"), "bytes": current.get("content_size_bytes"), "stats": current["content_stats"]})
    root.discovered_permissions_json = {**current, "content_previous": history[:KEEP_PREVIOUS], "content_stats": chosen["stats"],
                                        "content_size_bytes": chosen.get("bytes"), "content_updated_at": chosen.get("at"), "content_interim": False}
    db.commit()
    return True
