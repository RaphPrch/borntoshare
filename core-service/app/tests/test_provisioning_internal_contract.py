from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.internal_auth import require_internal
from app.utils.status_validation import ensure_transition, validate_job_invariants


def test_forbidden_transition_done_to_running() -> None:
    with pytest.raises(HTTPException) as exc:
        ensure_transition(current="DONE", next_status="RUNNING")
    assert exc.value.status_code == 409


def test_job_failed_requires_error_code() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_job_invariants(status_value="FAILED", finished_at=None, error_code=None)
    assert exc.value.status_code == 422


def test_scoped_auth_missing_scope_forbidden(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_TOKEN_MODE", "static")
    monkeypatch.setenv("INTERNAL_TOKEN", "svc-token")
    dep = require_internal({"profiles:write"}).dependency

    class _Req:
        headers = {}

    with pytest.raises(HTTPException) as exc:
        dep(
            request=_Req(),
            x_internal_token="svc-token",
            x_service_name="capsule",
            x_service_scope="jobs:read,jobs:write,events:write",
        )
    assert exc.value.status_code == 403


def test_scoped_auth_invalid_token_unauthorized(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_TOKEN_MODE", "static")
    monkeypatch.setenv("INTERNAL_TOKEN", "svc-token")
    dep = require_internal({"jobs:read"}).dependency

    class _Req:
        headers = {}

    with pytest.raises(HTTPException) as exc:
        dep(
            request=_Req(),
            x_internal_token="wrong",
            x_service_name="governance",
            x_service_scope="jobs:read,jobs:write,profiles:write,events:write",
        )
    assert exc.value.status_code == 403

