from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.security.internal_auth import require_internal
from app.utils.status_validation import ensure_transition, validate_job_invariants, validate_profile_invariants


def _retry_backoff_minutes(attempt_count: int) -> int:
    table = [1, 5, 15, 60]
    idx = max(0, min(int(attempt_count) - 1, len(table) - 1))
    return table[idx]


def _next_retry_attempt_count(job_attempt_count: int | None, profile_attempt_count: int | None) -> int:
    return max(int(job_attempt_count or 0), int(profile_attempt_count or 0)) + 1


def test_forbidden_transition_done_to_running() -> None:
    with pytest.raises(HTTPException) as exc:
        ensure_transition(current="DONE", next_status="RUNNING")
    assert exc.value.status_code == 409


def test_profile_done_requires_group_external_id() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_profile_invariants(status_value="DONE", group_external_id=None, error_code=None)
    assert exc.value.status_code == 422


def test_job_failed_requires_error_code() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_job_invariants(status_value="FAILED", finished_at=None, error_code=None)
    assert exc.value.status_code == 422


def test_scoped_auth_missing_scope_forbidden(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", "svc-token")
    dep = require_internal({"profiles:write"}).dependency

    class _Req:
        headers = {}

    with pytest.raises(HTTPException) as exc:
        dep(
            request=_Req(),
            x_service_token="svc-token",
            x_internal_token="",
            x_service_name="capsule",
            x_service_scope="jobs:read,jobs:write,events:write",
        )
    assert exc.value.status_code == 403


def test_scoped_auth_invalid_token_unauthorized(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", "svc-token")
    dep = require_internal({"jobs:read"}).dependency

    class _Req:
        headers = {}

    with pytest.raises(HTTPException) as exc:
        dep(
            request=_Req(),
            x_service_token="wrong",
            x_internal_token="",
            x_service_name="governance",
            x_service_scope="jobs:read,jobs:write,profiles:write,events:write",
        )
    assert exc.value.status_code == 401


def test_retry_policy_next_attempt_uses_max_between_job_and_profile() -> None:
    assert _next_retry_attempt_count(1, 4) == 5
    assert _next_retry_attempt_count(4, 1) == 5
    assert _next_retry_attempt_count(0, 0) == 1


def test_retry_policy_backoff_table_is_stable_and_capped() -> None:
    assert _retry_backoff_minutes(1) == 1
    assert _retry_backoff_minutes(2) == 5
    assert _retry_backoff_minutes(3) == 15
    assert _retry_backoff_minutes(4) == 60
    assert _retry_backoff_minutes(8) == 60
