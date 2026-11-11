"""Observability › Jobs: what each job worked on, how long it waited and ran, whether it is stuck, and the
operator actions (retry a failed one, flush the stuck ones)."""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

ACTIVE = {"CREATED", "QUEUED", "RUNNING", "RETRYING"}
# Waiting longer than this in the queue: no worker is taking it
QUEUE_STUCK_SECONDS = 300
# Probes that only read and whose result is filed from their payload: running them again is safe
RETRYABLE_ACTIONS = {
    "scan_smb_sensitivity", "folder_scan", "test_smb_root_access", "test_smb_ntlm", "test_ldap", "test_ldaps",
    "fetch_tls_certificate", "resolve_name",
}
# Where the others are started again (their result is tied to a request, a snapshot…)
RETRY_ELSEWHERE = {
    "DIRECTORY_SNAPSHOT": "Identity sources › Synchronise",
    "AD_ACCESS_GRANT": "Access requests",
    "AD_GROUP_MEMBERSHIP_REMOVE": "Access requests",
    "ACL_APPLY": "Folders › Permissions",
    "INFRA_HEALTH": "Observability › Health (runs every few minutes)",
}
_SECRET_KEY = re.compile(r"pass(word)?|secret(?!_ref)|token|private|credential", re.IGNORECASE)


def _load(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except ValueError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def envelope(row: dict[str, Any]) -> dict[str, Any]:
    """The probe payload ({template, kind, target, auth, options, context}) or the flat payload of the other jobs."""
    payload = _load(row.get("payload_json"))
    inner = payload.get("payload")
    return inner if isinstance(inner, dict) else payload


def timeout_seconds(row: dict[str, Any]) -> int:
    body = envelope(row)
    options = body.get("options") if isinstance(body.get("options"), dict) else {}
    for value in (options.get("timeout_sec"), body.get("timeout")):
        try:
            if value:
                return max(1, int(value))
        except (TypeError, ValueError):
            continue
    return 30


def stuck_reason(row: dict[str, Any]) -> str | None:
    """Why a job is considered stuck (None when it is not): nobody took it, or it runs far beyond its timeout
    (the rule probes already apply to themselves: three times the timeout, at least 90 s)."""
    status = str(row.get("status") or "").upper()
    if status in {"QUEUED", "RETRYING", "CREATED"} and int(row.get("wait_seconds") or row.get("queue_age_seconds") or 0) > QUEUE_STUCK_SECONDS:
        return "queue"
    if status == "RUNNING" and int(row.get("run_seconds") or 0) > max(90, timeout_seconds(row) * 3):
        return "running"
    return None


def _int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _names(db: Session, table: str, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    try:
        rows = db.execute(
            text(f"SELECT id, name FROM {table} WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)), {"ids": sorted(ids)}
        ).all()
    except Exception:
        db.rollback()
        return {}
    return {int(row_id): str(name) for row_id, name in rows}


def _origin(row: dict[str, Any]) -> str:
    body = envelope(row)
    context = body.get("context") if isinstance(body.get("context"), dict) else {}
    if context.get("retry_of"):
        return "retry"
    if context.get("policy_id"):
        return "policy"
    origin = str(context.get("ui_origin") or body.get("trigger") or "").strip().lower()
    return origin or "platform"


def _queue(job_type: Any) -> str | None:
    from app.jobs.b2s_job_contracts.contracts import queue_for_job_type

    try:
        return str(queue_for_job_type(job_type)).removeprefix("capsule_")
    except Exception:
        return None


def summarize(db: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each job with: target (what it worked on and its page), origin, wait / run durations, attempts, stuck,
    retryable. The bulky payload and result stay for the detail."""
    roots, endpoints, sources = set(), set(), set()
    for row in rows:
        body = envelope(row)
        target = body.get("target") if isinstance(body.get("target"), dict) else {}
        context = body.get("context") if isinstance(body.get("context"), dict) else {}
        root_id = _int(context.get("storage_root_id") or target.get("storage_root_id"))
        endpoint_id = _int(context.get("storage_endpoint_id") or target.get("storage_endpoint_id"))
        source_id = _int(row.get("identity_source_id") or body.get("identity_source_id"))
        row["_ids"] = (root_id, endpoint_id, source_id)
        roots.update([root_id] if root_id else [])
        endpoints.update([endpoint_id] if endpoint_id else [])
        sources.update([source_id] if source_id else [])
    root_names = _names(db, "storage_roots", roots)
    endpoint_names = _names(db, "storage_endpoints", endpoints)
    source_names = _names(db, "identity_sources", sources)

    out = []
    for row in rows:
        root_id, endpoint_id, source_id = row.pop("_ids")
        body = envelope(row)
        target = body.get("target") if isinstance(body.get("target"), dict) else {}
        if root_id:
            subject = {"kind": "folder", "id": root_id, "label": root_names.get(root_id) or f"#{root_id}",
                       "href": f"/storage-roots?selected={root_id}"}
        elif endpoint_id:
            subject = {"kind": "server", "id": endpoint_id, "label": endpoint_names.get(endpoint_id) or f"#{endpoint_id}",
                       "href": f"/admin/storage-endpoints/{endpoint_id}"}
        elif source_id:
            subject = {"kind": "directory", "id": source_id, "label": source_names.get(source_id) or f"#{source_id}",
                       "href": "/admin/identity-sources"}
        elif target.get("host") or target.get("name"):
            label = str(target.get("host") or target.get("name"))
            subject = {"kind": "host", "id": None, "label": f"{label}:{target['port']}" if target.get("port") else label, "href": None}
        else:
            subject = None
        if subject and body.get("group_name"):
            subject["detail"] = str(body.get("group_name"))
        metrics = _load(row.get("metrics_json"))
        action = str(row.get("action") or "")
        status = str(row.get("status") or "").upper()
        out.append({
            "id": row.get("id"),
            "correlation_id": row.get("correlation_id"),
            "job_type": row.get("job_type"),
            "action": action,
            "status": status,
            "identity_source_id": row.get("identity_source_id"),
            "error_code": row.get("error_code"),
            "error_message": row.get("error_message"),
            "created_at": row.get("created_at"),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "updated_at": row.get("updated_at"),
            "queue_age_seconds": row.get("queue_age_seconds"),
            "wait_seconds": row.get("wait_seconds"),
            "run_seconds": row.get("run_seconds"),
            "timeout_seconds": timeout_seconds(row),
            "queue": _queue(row.get("job_type")),
            "attempts": 1 + int(metrics.get("retries") or 0),
            "requested_by": metrics.get("requested_by"),
            "watchdog_republish_count": int(row.get("watchdog_republish_count") or 0),
            "target": subject,
            "origin": _origin(row),
            "retry_of": _int((body.get("context") or {}).get("retry_of")) if isinstance(body.get("context"), dict) else None,
            "stuck": stuck_reason(row),
            "retryable": action in RETRYABLE_ACTIONS and status in {"FAILED", "CANCELLED"},
            "retry_elsewhere": RETRY_ELSEWHERE.get(str(row.get("job_type") or "").upper()) if action not in RETRYABLE_ACTIONS else None,
        })
    return out


def redact(value: Any) -> Any:
    """Payload shown to the operator: no secret values (secret_ref, a reference, stays)."""
    if isinstance(value, dict):
        return {key: ("••••" if _SECRET_KEY.search(str(key)) and value[key] else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def summarize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """summarize() with its own session (for the orchestration routes, which hold none)."""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        return summarize(db, [dict(row) for row in rows])


def after_retry(summary: dict[str, Any], new_job_id: int | None, *, actor_id: int | None, actor_display: str | None) -> None:
    """The folder of a retried scan or measure shows it running, and the retry is in the activity."""
    from app.core.db import SessionLocal
    from app.services import scans, sensitivity
    from app.services.activity_log import log_activity

    target = summary.get("target") or {}
    root_id = target.get("id") if target.get("kind") == "folder" else None
    with SessionLocal() as db:
        if root_id and summary.get("action") == sensitivity.ACTION:
            sensitivity.mark_requested(db, int(root_id), new_job_id)
        elif root_id and summary.get("action") == scans.ACTION:
            scans.mark_requested(db, int(root_id), new_job_id)
        log_activity(db, actor_type="user", actor_id=actor_id, actor_display=actor_display, action="job.retried", outcome="success",
                     target_type="job", target_id=int(summary["id"]), target_display=str(summary.get("job_type") or ""),
                     context_json={"new_job_id": new_job_id, "job_action": summary.get("action")})


def log_flush(job_ids: list[int], *, actor_id: int | None, actor_display: str | None) -> None:
    from app.core.db import SessionLocal
    from app.services.activity_log import log_activity

    with SessionLocal() as db:
        log_activity(db, actor_type="user", actor_id=actor_id, actor_display=actor_display, action="job.flushed", outcome="success",
                     target_type="job", target_display=f"{len(job_ids)} job(s)", context_json={"job_ids": job_ids})


def retry_payload(row: dict[str, Any]) -> dict[str, Any]:
    """The payload of a job to run again: the same, marked as a retry of it; a sensitivity scan starts again from
    where the folder's last scan stopped (not where this one did)."""
    payload = _load(row.get("payload_json"))
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    context = dict(body.get("context") or {}) if isinstance(body.get("context"), dict) else {}
    context["retry_of"] = int(row["id"])
    body["context"] = context
    if str(row.get("action") or "") == "scan_smb_sensitivity":
        from app.services.sensitivity import incremental_params

        target = dict(body.get("target") or {})
        root_id = _int(context.get("storage_root_id") or target.get("storage_root_id"))
        if root_id:
            target.update(incremental_params(root_id))
            body["target"] = target
    return payload


# How long the history of the jobs is kept (days); the routine health checks pile up, they go first
KEEP_DAYS = {"health": 2, "succeeded": 30, "finished": 90}
PURGE_BATCH = 5000


def purge_history(db: Session) -> int:
    """Old finished jobs are deleted (never a queued or running one), a batch at a time. Returns how many."""
    rules = [
        ("UPPER(job_type) = 'INFRA_HEALTH' AND UPPER(status) = 'SUCCEEDED'", KEEP_DAYS["health"]),
        ("UPPER(status) = 'SUCCEEDED'", KEEP_DAYS["succeeded"]),
        ("UPPER(status) IN ('FAILED', 'CANCELLED')", KEEP_DAYS["finished"]),
    ]
    total = 0
    for condition, days in rules:
        result = db.execute(
            text(f"DELETE FROM provisioning_jobs WHERE {condition} AND created_at < UTC_TIMESTAMP() - INTERVAL :days DAY LIMIT :batch"),
            {"days": int(days), "batch": PURGE_BATCH},
        )
        total += int(result.rowcount or 0)
    db.commit()
    return total
