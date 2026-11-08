"""Sensitivity of the governed folders: what the capsule runner found in them (passwords, keys, vaults).

One row per folder (storage_root_sensitivity, pack 149): the last scan, its counts and its findings.
Only paths, rules, line numbers and masked excerpts are stored: never a secret.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

ACTION = "scan_smb_sensitivity"
CATEGORIES = ("password", "credentials_file", "password_vault", "private_key", "cloud_key")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def mark_requested(db: Session, storage_root_id: int, job_id: int | None) -> None:
    db.execute(
        text(
            """
            INSERT INTO storage_root_sensitivity (storage_root_id, status, job_id, requested_at)
            VALUES (:id, 'running', :job, :now)
            ON DUPLICATE KEY UPDATE status = 'running', job_id = VALUES(job_id), requested_at = VALUES(requested_at), error_message = NULL
            """
        ),
        {"id": int(storage_root_id), "job": job_id, "now": _now()},
    )
    db.commit()


def record_result(db: Session, storage_root_id: int, job_id: int | None, result_json: dict | None) -> dict[str, Any] | None:
    details = (result_json or {}).get("details") if isinstance(result_json, dict) else None
    scan = details.get("sensitivity") if isinstance(details, dict) else None
    if not isinstance(scan, dict):
        return None
    summary = {key: scan.get(key) for key in ("rules_version", "target", "files_listed", "files_read", "bytes_read", "truncated")}
    db.execute(
        text(
            """
            INSERT INTO storage_root_sensitivity
              (storage_root_id, status, files_flagged, counts_json, findings_json, summary_json, job_id, scanned_at, error_message)
            VALUES (:id, 'done', :flagged, :counts, :findings, :summary, :job, :now, NULL)
            ON DUPLICATE KEY UPDATE status = 'done', files_flagged = VALUES(files_flagged), counts_json = VALUES(counts_json),
              findings_json = VALUES(findings_json), summary_json = VALUES(summary_json), job_id = VALUES(job_id),
              scanned_at = VALUES(scanned_at), error_message = NULL
            """
        ),
        {
            "id": int(storage_root_id),
            "flagged": int(scan.get("files_flagged") or 0),
            "counts": json.dumps(scan.get("counts") or {}),
            "findings": json.dumps(scan.get("findings") or []),
            "summary": json.dumps(summary),
            "job": job_id,
            "now": _now(),
        },
    )
    return scan


def record_failure(db: Session, storage_root_id: int, job_id: int | None, message: str | None) -> None:
    db.execute(
        text(
            """
            INSERT INTO storage_root_sensitivity (storage_root_id, status, job_id, error_message)
            VALUES (:id, 'failed', :job, :message)
            ON DUPLICATE KEY UPDATE status = 'failed', job_id = VALUES(job_id), error_message = VALUES(error_message)
            """
        ),
        {"id": int(storage_root_id), "job": job_id, "message": str(message or "The scan failed")[:500]},
    )


def _load(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def get(db: Session, storage_root_id: int) -> dict[str, Any] | None:
    try:
        row = db.execute(
            text("SELECT * FROM storage_root_sensitivity WHERE storage_root_id = :id"), {"id": int(storage_root_id)}
        ).mappings().first()
    except Exception:
        db.rollback()
        return None
    if row is None:
        return None
    iso = lambda value: value.isoformat() + "Z" if value else None  # noqa: E731
    return {
        "status": row["status"],
        "files_flagged": int(row["files_flagged"] or 0),
        "counts": _load(row["counts_json"], {}),
        "findings": _load(row["findings_json"], []),
        **(_load(row["summary_json"], {}) or {}),
        "error": row["error_message"],
        "requested_at": iso(row["requested_at"]),
        "scanned_at": iso(row["scanned_at"]),
    }


def flagged_by_root(db: Session, storage_root_ids: list[int]) -> dict[int, int]:
    """Files flagged per folder, for the list (express search « est:sensible »)."""
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {}
    try:
        rows = db.execute(
            text("SELECT storage_root_id, files_flagged FROM storage_root_sensitivity WHERE status = 'done' AND storage_root_id IN :ids")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).all()
    except Exception:
        db.rollback()
        return {}
    return {int(root_id): int(flagged or 0) for root_id, flagged in rows}
