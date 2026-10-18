from __future__ import annotations

from typing import Optional

from fastapi import HTTPException


MAX_RETRY_ATTEMPTS = 5
RETRY_BACKOFF_MINUTES: tuple[int, ...] = (1, 5, 15, 60)


def ensure_retryable_status(status_value: str) -> None:
    current = str(status_value or "").strip().upper()
    if current not in {"FAILED", "RETRYING"}:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "GOVERNANCE_RETRY_REJECTED",
                "message": "Retry allowed only when job status is FAILED or RETRYING",
            },
        )


def next_retry_attempt(job_attempt: int | None, profile_attempt: int | None) -> int:
    return max(int(job_attempt or 0), int(profile_attempt or 0)) + 1


def ensure_retry_attempt_allowed(next_attempt: int) -> None:
    if int(next_attempt) > int(MAX_RETRY_ATTEMPTS):
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "GOVERNANCE_RETRY_LIMIT_REACHED",
                "message": f"Retry limit reached (max={MAX_RETRY_ATTEMPTS})",
            },
        )


def retry_backoff_minutes(attempt_count: int | None) -> int:
    attempt = max(1, int(attempt_count or 1))
    idx = max(0, min(attempt - 1, len(RETRY_BACKOFF_MINUTES) - 1))
    return int(RETRY_BACKOFF_MINUTES[idx])
