from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status


TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}
RUNNABLE_STATUSES = {"CREATED", "QUEUED", "RETRYING"}
KNOWN_STATUSES = RUNNABLE_STATUSES | {"RUNNING"} | TERMINAL_STATUSES


def normalize_status(value: str | None) -> str:
    raw = str(value or "").strip().upper()
    aliases = {
        "PENDING": "QUEUED",
        "QUEUE": "QUEUED",
        "SUCCESS": "SUCCEEDED",
        "DONE": "SUCCEEDED",
        "OK": "SUCCEEDED",
        "ACTIVE": "RUNNING",
        "CANCELED": "CANCELLED",
    }
    normalized = aliases.get(raw, raw)
    return normalized or "QUEUED"


def ensure_transition(*, current: str | None, next_status: str | None) -> str:
    cur = normalize_status(current)
    nxt = normalize_status(next_status)

    if nxt not in KNOWN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported status transition target: {nxt}",
        )

    if cur in {"SUCCEEDED", "FAILED"} and nxt not in {cur, "CANCELLED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Illegal status transition {cur} -> {nxt}",
        )

    if cur == "CANCELLED" and nxt != "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Illegal status transition {cur} -> {nxt}",
        )

    if cur == "RUNNING" and nxt in {"CREATED", "QUEUED", "RETRYING"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Illegal status transition {cur} -> {nxt}",
        )

    if cur in RUNNABLE_STATUSES and nxt in RUNNABLE_STATUSES:
        # Allow idempotent/recovery loops among queueing states.
        return nxt

    if cur == "RUNNING" and nxt in TERMINAL_STATUSES:
        return nxt

    if cur in RUNNABLE_STATUSES and nxt == "RUNNING":
        return nxt

    if cur == nxt:
        return nxt

    # Conservative fallback for yet-unmodelled but known transitions.
    return nxt


def validate_job_invariants(*, status_value: str | None, finished_at: datetime | None, error_code: str | None) -> None:
    st = normalize_status(status_value)
    if st == "FAILED" and not str(error_code or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="error_code is required when status=FAILED",
        )
    if st in {"SUCCEEDED", "FAILED", "CANCELLED"} and finished_at is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="finished_at is required for terminal job status",
        )


def validate_profile_invariants(*, status_value: str | None, group_external_id: str | None, error_code: str | None) -> None:
    st = normalize_status(status_value)
    if st == "SUCCEEDED" and not str(group_external_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="group_external_id is required when profile status=SUCCEEDED",
        )
    if st == "FAILED" and not str(error_code or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="error_code is required when profile status=FAILED",
        )

