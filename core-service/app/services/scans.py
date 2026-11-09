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
    return {"status": row["status"], "job_id": row["job_id"], "method": row["method"], "fallback_reason": row["fallback_reason"],
            "requested_at": _iso(row["requested_at"]), "finished_at": _iso(row["finished_at"]), "elapsed_ms": row["elapsed_ms"],
            "files": row["files"], "error": row["error_message"]}


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
    # A new dict: the JSON column is seen as changed (the ACL part of the last test stays as it is)
    root.discovered_permissions_json = {**current, "content_size_bytes": int(stats.get("bytes") or 0),
                                        "content_updated_at": now.isoformat() + "+00:00", "content_stats": stats,
                                        "content_scan_job_id": job_id}
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
    return True


def record_failure(db: Session, storage_root_id: int, job_id: int | None, message: str | None) -> None:
    db.execute(
        text("UPDATE storage_root_scans SET status = 'failed', job_id = :job, finished_at = :now, error_message = :message WHERE storage_root_id = :id"),
        {"id": int(storage_root_id), "job": job_id, "now": _now(), "message": (message or "")[:600]},
    )
    db.commit()


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


