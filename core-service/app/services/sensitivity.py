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
# What « est:mot-de-passe » means: a password written in clear, a file named after passwords, a password vault
PASSWORD_CATEGORIES = ("password", "credentials_file", "password_vault")
# What « est:cle-ou-jeton » means: a private key, an API key or token
KEY_CATEGORIES = ("private_key", "cloud_key")
# Rules version 3 of the worker: numbers checked by their checksum, files that should not sit in a data share
PERSONAL_CATEGORIES = ("personal_data",)
BANK_CATEGORIES = ("bank_data",)
RISKY_CATEGORIES = ("backup_database", "mailbox", "executable")
# What a folder row says (and the express search reads): files of each group, None when never scanned
FILE_GROUPS = {
    "password_files": PASSWORD_CATEGORIES,
    "key_files": KEY_CATEGORIES,
    "personal_files": PERSONAL_CATEGORIES,
    "bank_files": BANK_CATEGORIES,
    "risky_files": RISKY_CATEGORIES,
}


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


def _ignored_paths(value: Any) -> set[str]:
    return {str(item.get("path", "")).lower() for item in _load(value, []) if isinstance(item, dict)}


def visible(findings: list[dict], ignored: set[str], total_flagged: int | None = None) -> tuple[int, dict[str, int]]:
    """Files flagged and counts per category, without the files marked as false positives. The worker keeps at
    most 100 findings: files beyond them (total_flagged) still count."""
    listed = {str(item.get("path", "")).lower() for item in findings}
    shown = [item for item in findings if str(item.get("path", "")).lower() not in ignored]
    counts: dict[str, int] = {}
    for item in shown:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    unlisted = max(0, int(total_flagged or 0) - len(listed))
    return len({str(item.get("path", "")).lower() for item in shown}) + unlisted, counts


def _merge(previous: list[dict], scan: dict, same_rules: bool) -> list[dict]:
    """Findings after an incremental scan: the names of all the files were checked again (their findings replace the
    old ones); the content only of the files read this time. A file not read again keeps its content findings,
    unless it is gone or the rules changed."""
    new = list(scan.get("findings") or [])
    incremental = scan.get("incremental") if isinstance(scan.get("incremental"), dict) else None
    if incremental is None:
        return new
    read = {str(path).lower() for path in incremental.get("read_paths") or []}
    gone = {str(path).lower() for path in incremental.get("gone_paths") or []}
    kept = [item for item in previous
            if same_rules and item.get("line") is not None
            and str(item.get("path", "")).lower() not in read and str(item.get("path", "")).lower() not in gone]
    unique: dict[tuple[str, str], dict] = {}
    for item in [*kept, *new]:
        key = (str(item.get("path", "")).lower(), str(item.get("category")))
        if key not in unique or (unique[key].get("line") is None and item.get("line") is not None):
            unique[key] = item
    return list(unique.values())


def incremental_params(storage_root_id: int) -> dict[str, Any]:
    """Where the next scan of the folder starts, and the files whose content was flagged (to know if they are gone)."""
    from app.core.db import SessionLocal

    if not storage_root_id:
        return {}
    session = SessionLocal()
    try:
        row = session.execute(
            text("SELECT content_since, content_cursor, rules_version, findings_json FROM storage_root_sensitivity WHERE storage_root_id = :id"),
            {"id": int(storage_root_id)},
        ).mappings().first()
    except Exception:
        return {}
    finally:
        session.close()
    if not row or not row["content_since"]:
        return {}
    known = sorted({str(item.get("path")) for item in _load(row["findings_json"], []) if isinstance(item, dict) and item.get("line") is not None})
    return {"since": row["content_since"], "cursor_path": row["content_cursor"] or "", "rules_version": row["rules_version"], "known_paths": known[:200]}


def record_result(db: Session, storage_root_id: int, job_id: int | None, result_json: dict | None) -> dict[str, Any] | None:
    details = (result_json or {}).get("details") if isinstance(result_json, dict) else None
    scan = details.get("sensitivity") if isinstance(details, dict) else None
    if not isinstance(scan, dict):
        return None
    previous = db.execute(text("SELECT ignored_json, findings_json, rules_version FROM storage_root_sensitivity WHERE storage_root_id = :id"),
                          {"id": int(storage_root_id)}).mappings().first()
    same_rules = bool(previous) and previous["rules_version"] == scan.get("rules_version")
    findings = _merge(_load(previous["findings_json"], []) if previous else [], scan, same_rules)
    incremental = scan.get("incremental") if isinstance(scan.get("incremental"), dict) else {}
    summary = {key: scan.get(key) for key in ("rules_version", "target", "files_listed", "files_read", "bytes_read", "truncated", "method", "fallback_reason")}
    summary["files_flagged_total"] = len({str(item.get("path", "")).lower() for item in findings})
    summary["incremental"] = {key: incremental.get(key) for key in ("full", "complete", "pending")}
    # The files marked as false positives stay so through the new scan
    flagged, counts = visible(findings, _ignored_paths(previous["ignored_json"] if previous else None), summary["files_flagged_total"])
    db.execute(
        text(
            """
            INSERT INTO storage_root_sensitivity
              (storage_root_id, status, files_flagged, counts_json, findings_json, summary_json, job_id, scanned_at, error_message,
               content_since, content_cursor, content_pending, content_complete, rules_version)
            VALUES (:id, 'done', :flagged, :counts, :findings, :summary, :job, :now, NULL, :since, :cursor, :pending, :complete, :rules)
            ON DUPLICATE KEY UPDATE status = 'done', files_flagged = VALUES(files_flagged), counts_json = VALUES(counts_json),
              findings_json = VALUES(findings_json), summary_json = VALUES(summary_json), job_id = VALUES(job_id),
              scanned_at = VALUES(scanned_at), error_message = NULL, content_since = VALUES(content_since),
              content_cursor = VALUES(content_cursor), content_pending = VALUES(content_pending),
              content_complete = VALUES(content_complete), rules_version = VALUES(rules_version)
            """
        ),
        {
            "id": int(storage_root_id),
            "flagged": flagged,
            "counts": json.dumps(counts),
            "findings": json.dumps(findings[:500]),
            "summary": json.dumps(summary),
            "job": job_id,
            "now": _now(),
            "since": incremental.get("next_since"),
            "cursor": (incremental.get("next_cursor") or None) and str(incremental["next_cursor"])[:1024],
            "pending": incremental.get("pending"),
            "complete": None if not incremental else (1 if incremental.get("complete") else 0),
            "rules": scan.get("rules_version"),
        },
    )
    return scan


def set_ignored(db: Session, storage_root_id: int, path: str, ignore: bool, by: str | None, reason: str | None = None) -> dict[str, Any] | None:
    """Mark a file as a false positive (or not any more), and count again."""
    row = db.execute(
        text("SELECT findings_json, summary_json, ignored_json FROM storage_root_sensitivity WHERE storage_root_id = :id"),
        {"id": int(storage_root_id)},
    ).mappings().first()
    if row is None:
        return None
    findings = _load(row["findings_json"], [])
    if not any(str(item.get("path", "")).lower() == path.lower() for item in findings):
        return None
    ignored = [item for item in _load(row["ignored_json"], []) if isinstance(item, dict) and str(item.get("path", "")).lower() != path.lower()]
    if ignore:
        ignored.append({"path": path, "by": by, "at": _now().isoformat() + "Z", "reason": reason})
    summary = _load(row["summary_json"], {})
    flagged, counts = visible(findings, {str(item["path"]).lower() for item in ignored}, summary.get("files_flagged_total"))
    db.execute(
        text("UPDATE storage_root_sensitivity SET ignored_json = :ignored, files_flagged = :flagged, counts_json = :counts WHERE storage_root_id = :id"),
        {"ignored": json.dumps(ignored), "flagged": flagged, "counts": json.dumps(counts), "id": int(storage_root_id)},
    )
    db.commit()
    return get(db, storage_root_id)


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
    ignored = _ignored_paths(row.get("ignored_json"))
    reasons = {str(item.get("path", "")).lower(): item for item in _load(row.get("ignored_json"), []) if isinstance(item, dict)}
    return {
        "status": row["status"],
        "files_flagged": int(row["files_flagged"] or 0),
        "counts": _load(row["counts_json"], {}),
        "findings": [
            {**item, "ignored": str(item.get("path", "")).lower() in ignored,
             "ignored_reason": (reasons.get(str(item.get("path", "")).lower()) or {}).get("reason"),
             "ignored_by": (reasons.get(str(item.get("path", "")).lower()) or {}).get("by")}
            for item in _load(row["findings_json"], [])
        ],
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


def files_by_root(db: Session, storage_root_ids: list[int], categories: tuple[str, ...]) -> dict[int, int]:
    """Files of these categories per scanned folder (without the false positives)."""
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {}
    try:
        rows = db.execute(
            text("SELECT storage_root_id, findings_json, ignored_json FROM storage_root_sensitivity WHERE status = 'done' AND storage_root_id IN :ids")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).all()
    except Exception:
        db.rollback()
        return {}
    out: dict[int, int] = {}
    for root_id, findings, ignored_json in rows:
        ignored = _ignored_paths(ignored_json)
        paths = {str(item.get("path", "")).lower() for item in _load(findings, [])
                 if isinstance(item, dict) and item.get("category") in categories}
        out[int(root_id)] = len(paths - ignored)
    return out


def file_groups_by_root(db: Session, storage_root_ids: list[int]) -> dict[int, dict[str, int]]:
    """{root: {password_files, key_files, personal_files, bank_files, risky_files}} in one reading of the results
    (without the false positives); a folder never scanned is absent."""
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {}
    try:
        rows = db.execute(
            text("SELECT storage_root_id, findings_json, ignored_json FROM storage_root_sensitivity WHERE status = 'done' AND storage_root_id IN :ids")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).all()
    except Exception:
        db.rollback()
        return {}
    out: dict[int, dict[str, int]] = {}
    for root_id, findings, ignored_json in rows:
        ignored = _ignored_paths(ignored_json)
        items = [item for item in _load(findings, []) if isinstance(item, dict)]
        out[int(root_id)] = {
            group: len({str(item.get("path", "")).lower() for item in items if item.get("category") in categories} - ignored)
            for group, categories in FILE_GROUPS.items()
        }
    return out


def password_files_by_root(db: Session, storage_root_ids: list[int]) -> dict[int, int]:
    """Files holding passwords per scanned folder: « est:mot-de-passe »."""
    return files_by_root(db, storage_root_ids, PASSWORD_CATEGORIES)


def key_files_by_root(db: Session, storage_root_ids: list[int]) -> dict[int, int]:
    """Private keys and API keys or tokens per scanned folder: « est:cle-ou-jeton »."""
    return files_by_root(db, storage_root_ids, KEY_CATEGORIES)


# A folder too big for one pass is read pass after pass, by itself, until its content is read through
MAX_PASSES = 1000


def continue_if_pending(db: Session, job_row: Any, scan: dict | None) -> int | None:
    """After a pass that left files to read: the next pass, queued at once (same parameters, the folder's new
    cursor). Stops when everything is read, when a pass made no progress, when another scan of the folder took
    over, or after MAX_PASSES. Returns the new job id."""
    import uuid

    from app.data.repositories.provisioning_jobs_repo import ProvisioningJobsRepo
    from app.jobs.b2s_job_contracts.actors import publish_job

    incremental = (scan or {}).get("incremental") if isinstance((scan or {}).get("incremental"), dict) else {}
    pending = int(incremental.get("pending") or 0)
    if not incremental or incremental.get("complete") or pending <= 0:
        return None
    payload = _load(getattr(job_row, "payload_json", None), {})
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else None
    if body is None:
        return None
    context = dict(body.get("context") or {})
    target = dict(body.get("target") or {})
    root_id = int(context.get("storage_root_id") or target.get("storage_root_id") or 0)
    passes = int(context.get("pass") or 1)
    previous = context.get("pending_before")
    if not root_id or passes >= MAX_PASSES or (previous is not None and pending >= int(previous)):
        return None
    job_id = int(getattr(job_row, "id", 0) or 0)
    current = db.execute(text("SELECT job_id FROM storage_root_sensitivity WHERE storage_root_id = :id"), {"id": root_id}).scalar()
    if current is not None and int(current) != job_id:
        return None
    target.update(incremental_params(root_id))
    body["target"] = target
    body["context"] = {**context, "pass": passes + 1, "pending_before": pending, "continues": job_id}
    row = ProvisioningJobsRepo(db).create(data={
        "correlation_id": f"prb_{uuid.uuid4().hex}",
        "job_type": getattr(job_row, "job_type", None),
        "action": ACTION,
        "status": "QUEUED",
        "identity_source_id": getattr(job_row, "identity_source_id", None),
        "payload_json": payload,
    })
    new_id = int(row.id)
    mark_requested(db, root_id, new_id)
    publish_job(str(getattr(job_row, "job_type", "") or ""), new_id)
    return new_id
