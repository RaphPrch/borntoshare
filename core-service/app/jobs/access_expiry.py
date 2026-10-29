"""Expiry of the granted accesses (schedule « access_expiry », every 15 min by default).

An approved request whose items have all reached their end date is closed: the beneficiary is
removed from the AD group of each item through a worker (same steps as a revocation, the group and
its ACL are kept), then the request becomes « expired ». A removal that fails leaves the request
approved: it is tried again 6 h later, and the schedule reports « partial ». A person still granted the
same level by another request stays in the group.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

BATCH_SIZE = 50
# One run stays short (the scheduler runs the tasks one after the other)
TIME_BUDGET_SECONDS = 120
# A request whose removal failed (unreachable directory…) waits before the next attempt
RETRY_AFTER_SECONDS = 6 * 3600

_last_failure: dict[int, float] = {}


class _SystemRequest:
    """Stands for the HTTP request of the routes reused here: the scheduler acts as an administrator."""

    def __init__(self, request_id: str) -> None:
        self.headers = {
            "x-roles": "platform_admin",
            "x-actor-display": "access-expiry",
            "x-request-id": request_id,
        }


def due_request_ids(db: Session, *, limit: int = BATCH_SIZE) -> list[int]:
    """Approved requests, not revoked, whose items all have an end date in the past."""
    rows = db.execute(
        text(
            """
            SELECT ar.id
            FROM access_requests ar
            JOIN access_request_items ari ON ari.access_request_id = ar.id
            WHERE LOWER(COALESCE(ar.status, '')) IN ('approved', 'executed')
              AND ar.revoked_at IS NULL
            GROUP BY ar.id
            HAVING SUM(ari.expires_at IS NULL) = 0 AND MAX(ari.expires_at) <= UTC_TIMESTAMP()
            ORDER BY MAX(ari.expires_at)
            LIMIT :limit
            """
        ),
        {"limit": int(limit)},
    ).all()
    return [int(row[0]) for row in rows]


def _labels(db: Session, req_id: int) -> dict[str, str]:
    """Beneficiary and storage root names, for « The access of {user} on {root} reached its end date »."""
    row = db.execute(
        text(
            """
            SELECT
              COALESCE(JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.display_name')),
                       JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.username'))) AS user,
              sr.name AS root
            FROM access_requests ar
            JOIN access_request_items ari ON ari.access_request_id = ar.id
            LEFT JOIN storage_roots sr ON sr.id = ari.target_id AND ari.target_type = 'storage_root'
            WHERE ar.id = :id
            LIMIT 1
            """
        ),
        {"id": int(req_id)},
    ).mappings().first()
    return {k: str(v) for k, v in dict(row or {}).items() if v and str(v) != "null"}


async def run_access_expiry(db: Session, *, trigger: str) -> dict[str, Any]:
    from app.api.governance.access_requests import _journal, _revoke_request_memberships
    from app.services.activity_log import log_activity

    expired: list[int] = []
    failed: dict[int, str] = {}
    started = time.monotonic()
    now = time.monotonic()
    candidates = due_request_ids(db, limit=1000)
    waiting = [req_id for req_id in candidates if req_id in _last_failure and now - _last_failure[req_id] < RETRY_AFTER_SECONDS]
    due = [req_id for req_id in candidates if req_id not in waiting][:BATCH_SIZE]
    for req_id in due:
        if time.monotonic() - started > TIME_BUDGET_SECONDS:
            break
        correlation_id = f"exp_{req_id}_{uuid.uuid4().hex[:10]}"
        request = _SystemRequest(correlation_id)
        _journal("access_request_expiry_started", req_id=req_id, request=request, correlation_id=correlation_id, result="in_progress")
        try:
            failure = await _revoke_request_memberships(req_id=req_id, request=request, correlation_id=correlation_id)
        except Exception as exc:  # one request must not stop the others
            failure = str(exc)
        if failure:
            failed[req_id] = failure[:300]
            _last_failure[req_id] = time.monotonic()
            _journal(
                "access_request_expiry_failed", req_id=req_id, request=request, correlation_id=correlation_id,
                result="failure", severity="warning", message=failure[:500],
            )
            continue
        db.execute(
            text("UPDATE access_requests SET status = 'expired', updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
            {"id": req_id},
        )
        db.commit()
        log_activity(
            db,
            actor_type="system",
            actor_id=None,
            actor_display="access-expiry",
            action="access_request.expired",
            outcome="success",
            target_type="access_request",
            target_id=req_id,
            target_display=f"REQ-{req_id}",
            context_json={"trigger": trigger, **_labels(db, req_id)},
            correlation_id=correlation_id,
        )
        _journal("access_request_expired", req_id=req_id, request=request, correlation_id=correlation_id)
        expired.append(req_id)
        _last_failure.pop(req_id, None)

    if not expired and not failed:
        message = "No access to close" + (f" ({len(waiting)} waiting after a failure)" if waiting else "")
    else:
        message = f"{len(expired)} access(es) closed" + (f", {len(failed)} failed (retried in 6 h)" if failed else "")
        if waiting:
            message += f", {len(waiting)} waiting after a failure"
    return {
        "status": "partial" if failed else "success",
        "message": message,
        "expired_ids": expired,
        "failed": {str(k): v for k, v in failed.items()},
        "waiting_retry": waiting,
    }
