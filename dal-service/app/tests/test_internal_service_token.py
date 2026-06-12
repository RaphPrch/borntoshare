from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.security.internal_auth import require_service_token


def test_require_service_token_ok(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", "svc-token")
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    require_service_token("svc-token")


def test_require_service_token_missing_header(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", "svc-token")
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_service_token("")
    assert exc.value.status_code == 401


def test_require_service_token_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_service_token("anything")
    assert exc.value.status_code == 401


def test_require_service_token_no_internal_token_fallback_via_service_header(monkeypatch) -> None:
    monkeypatch.delenv("SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("INTERNAL_TOKEN", "change-me-in-v1")
    with pytest.raises(HTTPException) as exc:
        require_service_token("change-me-in-v1")
    assert exc.value.status_code == 401


def test_require_service_token_no_internal_token_fallback_via_internal_header(monkeypatch) -> None:
    monkeypatch.delenv("SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("INTERNAL_TOKEN", "change-me-in-v1")
    with pytest.raises(HTTPException) as exc:
        require_service_token("", "change-me-in-v1")
    assert exc.value.status_code == 401
