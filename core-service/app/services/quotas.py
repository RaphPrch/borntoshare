"""Quotas of the governed folders: the FSRM quota on the Windows file server, and the requests to raise it.

storage_root_quotas (pack 154) holds one row per folder: what an administrator asked (pending while the worker
applies it), then what the server answered (limit, use, peak) on its last reading. The server stays the truth: every
job reads the quota again after changing it.

storage_root_quota_requests: a guardian (or an administrator) asks for more room with a reason; an administrator
approves (the new limit goes to the server at once) or refuses with a note.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

READ_ACTION = "folder_quota_read"
APPLY_ACTION = "folder_quota_apply"
ACTIONS = {READ_ACTION, APPLY_ACTION}
MIN_LIMIT = 1024 * 1024
MAX_LIMIT = 1024 ** 5


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: Any) -> str | None:
    return value.isoformat() + "Z" if value else None


def _int(value: Any) -> int | None:
    return None if value is None else int(value)


def _row(row: Any) -> dict[str, Any]:
    limit, used = _int(row["limit_bytes"]), _int(row["used_bytes"])
    return {
        "status": row["status"],
        "limit_bytes": limit,
        "soft": bool(row["soft_limit"]),
        "warn_percent": int(row["warn_percent"] or 85),
        "used_bytes": used,
        "peak_bytes": _int(row["peak_bytes"]),
        "used_percent": round(used * 100 / limit, 1) if limit and used is not None else None,
        "local_path": row["local_path"],
        "server_status": row["server_status"],
        "job_id": _int(row["job_id"]),
        "pending_operation": row["pending_operation"],
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "read_at": _iso(row["read_at"]),
        "applied_at": _iso(row["applied_at"]),
        "updated_by": row["updated_by"],
        "updated_at": _iso(row["updated_at"]),
    }


def _request_row(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "storage_root_id": int(row["storage_root_id"]),
        "requested_by_identity_id": _int(row["requested_by_identity_id"]),
        "requested_by": row["requested_by"],
        "current_limit_bytes": _int(row["current_limit_bytes"]),
        "requested_limit_bytes": int(row["requested_limit_bytes"]),
        "reason": row["reason"],
        "status": row["status"],
        "decided_by": row["decided_by"],
        "decided_at": _iso(row["decided_at"]),
        "decision_note": row["decision_note"],
        "created_at": _iso(row["created_at"]),
        **({"folder_name": row["folder_name"], "root_path": row["root_path"]} if "folder_name" in row.keys() else {}),
    }


def get_quota(db: Session, storage_root_id: int) -> dict[str, Any] | None:
    row = db.execute(text("SELECT * FROM storage_root_quotas WHERE storage_root_id = :id"), {"id": int(storage_root_id)}).mappings().first()
    return _row(row) if row else None


def get(db: Session, storage_root_id: int) -> dict[str, Any]:
    """The quota of the folder, its pending request and the last decisions (the card of the folder)."""
    requests = db.execute(
        text("SELECT * FROM storage_root_quota_requests WHERE storage_root_id = :id ORDER BY created_at DESC, id DESC LIMIT 10"),
        {"id": int(storage_root_id)},
    ).mappings().all()
    rows = [_request_row(row) for row in requests]
    return {
        "quota": get_quota(db, storage_root_id),
        "pending_request": next((row for row in rows if row["status"] == "pending"), None),
        "requests": rows,
    }


def mark_pending(db: Session, storage_root_id: int, *, operation: str, job_id: int | None, by: str | None,
                 limit_bytes: int | None = None, soft: bool = False, warn_percent: int = 85) -> None:
    """A change (set, remove) or a reading is on its way to the server."""
    values = {"id": int(storage_root_id), "job": job_id, "op": operation, "by": by, "now": _now()}
    if operation == "set":
        db.execute(
            text(
                """
                INSERT INTO storage_root_quotas (storage_root_id, status, limit_bytes, soft_limit, warn_percent, job_id, pending_operation, updated_by)
                VALUES (:id, 'pending', :limit, :soft, :warn, :job, 'set', :by)
                ON DUPLICATE KEY UPDATE status = 'pending', limit_bytes = VALUES(limit_bytes), soft_limit = VALUES(soft_limit),
                  warn_percent = VALUES(warn_percent), job_id = VALUES(job_id), pending_operation = 'set', updated_by = VALUES(updated_by),
                  error_code = NULL, error_message = NULL
                """
            ),
            {**values, "limit": int(limit_bytes or 0), "soft": 1 if soft else 0, "warn": int(warn_percent)},
        )
    else:
        db.execute(
            text(
                """
                INSERT INTO storage_root_quotas (storage_root_id, status, job_id, pending_operation, updated_by)
                VALUES (:id, 'pending', :job, :op, :by)
                ON DUPLICATE KEY UPDATE job_id = VALUES(job_id), pending_operation = VALUES(pending_operation),
                  status = IF(VALUES(pending_operation) = 'read', status, 'pending'),
                  updated_by = IF(VALUES(pending_operation) = 'read', updated_by, VALUES(updated_by)),
                  error_code = NULL, error_message = NULL
                """
            ),
            values,
        )
    db.commit()


def record_result(db: Session, storage_root_id: int, job_id: int | None, result_json: dict | None) -> dict[str, Any] | None:
    """What the server answered: its quota after the operation, or none."""
    details = (result_json or {}).get("details") if isinstance(result_json, dict) else None
    quota = details.get("quota") if isinstance(details, dict) else None
    if not isinstance(quota, dict):
        return None
    operation = str(details.get("quota_operation") or "read")
    now = _now()
    exists = bool(quota.get("exists"))
    params = {
        "id": int(storage_root_id), "job": job_id, "now": now,
        "status": "applied" if exists else "none",
        "limit": _int(quota.get("limit_bytes")) if exists else None,
        "soft": 1 if quota.get("soft") else 0,
        "warn": int((quota.get("thresholds") or [85])[0] or 85) if exists else 85,
        "used": _int(quota.get("used_bytes")) if exists else None,
        "peak": _int(quota.get("peak_bytes")) if exists else None,
        "path": str(quota.get("local_path") or "")[:1024] or None,
        "server": str(quota.get("status") or "")[:64] or None,
        "applied": now if operation in {"set", "remove"} else None,
    }
    db.execute(
        text(
            """
            INSERT INTO storage_root_quotas (storage_root_id, status, limit_bytes, soft_limit, warn_percent, used_bytes, peak_bytes,
              local_path, server_status, job_id, pending_operation, read_at, applied_at)
            VALUES (:id, :status, :limit, :soft, :warn, :used, :peak, :path, :server, :job, NULL, :now, :applied)
            ON DUPLICATE KEY UPDATE status = VALUES(status), limit_bytes = VALUES(limit_bytes), soft_limit = VALUES(soft_limit),
              warn_percent = VALUES(warn_percent), used_bytes = VALUES(used_bytes), peak_bytes = VALUES(peak_bytes),
              local_path = VALUES(local_path), server_status = VALUES(server_status), job_id = VALUES(job_id),
              pending_operation = NULL, read_at = VALUES(read_at), applied_at = COALESCE(VALUES(applied_at), applied_at),
              error_code = NULL, error_message = NULL
            """
        ),
        params,
    )
    db.commit()
    return get_quota(db, storage_root_id)


def record_failure(db: Session, storage_root_id: int, job_id: int | None, code: str | None, message: str | None) -> None:
    """The server refused or could not be reached. A failed reading keeps the last known quota; a failed change
    leaves the folder in 'failed' with why."""
    row = db.execute(text("SELECT status, pending_operation FROM storage_root_quotas WHERE storage_root_id = :id"),
                     {"id": int(storage_root_id)}).mappings().first()
    if row is None:
        return
    changing = row["pending_operation"] in {"set", "remove"}
    db.execute(
        text(
            """
            UPDATE storage_root_quotas SET status = :status, pending_operation = NULL, job_id = :job,
              error_code = :code, error_message = :message WHERE storage_root_id = :id
            """
        ),
        {"id": int(storage_root_id), "job": job_id, "code": (code or "FAILED")[:64], "message": (message or "")[:600],
         "status": "failed" if changing or row["status"] == "pending" else row["status"]},
    )
    db.commit()


def by_root(db: Session, storage_root_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Quota per folder for the list (gauge, express search « est:quota », « est:quota-plein »)."""
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {}
    try:
        rows = db.execute(
            text(
                """
                SELECT q.storage_root_id, q.status, q.limit_bytes, q.used_bytes, q.warn_percent, q.soft_limit,
                       (SELECT COUNT(*) FROM storage_root_quota_requests r WHERE r.storage_root_id = q.storage_root_id AND r.status = 'pending') AS pending_requests
                FROM storage_root_quotas q WHERE q.storage_root_id IN :ids
                """
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).mappings().all()
    except Exception:
        db.rollback()
        return {}
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        limit, used = _int(row["limit_bytes"]), _int(row["used_bytes"])
        out[int(row["storage_root_id"])] = {
            "quota_status": row["status"],
            "quota_limit_bytes": limit if row["status"] != "none" else None,
            "quota_used_bytes": used,
            "quota_used_percent": round(used * 100 / limit, 1) if limit and used is not None and row["status"] == "applied" else None,
            "quota_warn_percent": int(row["warn_percent"] or 85),
            "quota_soft": bool(row["soft_limit"]),
            "quota_pending_requests": int(row["pending_requests"] or 0),
        }
    return out


# ---- requests to raise a quota ----

def create_request(db: Session, storage_root_id: int, *, requested_limit_bytes: int, reason: str,
                   identity_id: int | None, by: str | None) -> dict[str, Any]:
    current = get_quota(db, storage_root_id)
    result = db.execute(
        text(
            """
            INSERT INTO storage_root_quota_requests (storage_root_id, requested_by_identity_id, requested_by, current_limit_bytes,
              requested_limit_bytes, reason, status, created_at)
            VALUES (:id, :who_id, :who, :current, :wanted, :reason, 'pending', :now)
            """
        ),
        {"id": int(storage_root_id), "who_id": identity_id, "who": by, "current": (current or {}).get("limit_bytes"),
         "wanted": int(requested_limit_bytes), "reason": reason[:500], "now": _now()},
    )
    db.commit()
    return get_request(db, int(result.lastrowid))  # type: ignore[arg-type]


def get_request(db: Session, request_id: int) -> dict[str, Any] | None:
    row = db.execute(text("SELECT * FROM storage_root_quota_requests WHERE id = :id"), {"id": int(request_id)}).mappings().first()
    return _request_row(row) if row else None


def pending_request(db: Session, storage_root_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text("SELECT * FROM storage_root_quota_requests WHERE storage_root_id = :id AND status = 'pending' ORDER BY id DESC LIMIT 1"),
        {"id": int(storage_root_id)},
    ).mappings().first()
    return _request_row(row) if row else None


def decide_request(db: Session, request_id: int, *, status: str, by: str | None, note: str | None) -> dict[str, Any] | None:
    db.execute(
        text(
            """
            UPDATE storage_root_quota_requests SET status = :status, decided_by = :by, decided_at = :now, decision_note = :note
            WHERE id = :id AND status = 'pending'
            """
        ),
        {"id": int(request_id), "status": status, "by": by, "now": _now(), "note": (note or None) and note[:500]},
    )
    db.commit()
    return get_request(db, request_id)


def list_requests(db: Session, status: str | None = "pending", limit: int = 200) -> list[dict[str, Any]]:
    where = "WHERE r.status = :status" if status else ""
    rows = db.execute(
        text(
            f"""
            SELECT r.*, sr.name AS folder_name, sr.root_path
            FROM storage_root_quota_requests r JOIN storage_roots sr ON sr.id = r.storage_root_id
            {where} ORDER BY r.created_at DESC, r.id DESC LIMIT :limit
            """
        ),
        {"status": status, "limit": int(limit)},
    ).mappings().all()
    return [_request_row(row) for row in rows]


def describe(limit_bytes: int | None) -> str:
    """1.5 GB, 200 MB: the size in audit texts."""
    if not limit_bytes:
        return "—"
    value = float(limit_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}".replace(".0 ", " ")
        value /= 1024
    return json.dumps(limit_bytes)
