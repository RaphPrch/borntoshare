from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.internal_auth import _verify_internal_token


@pytest.fixture
def static_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN_MODE", "static")
    monkeypatch.setenv("INTERNAL_TOKEN", "shared-token")


def test_internal_token_ok(static_token) -> None:
    _verify_internal_token("shared-token")


def test_internal_token_missing_header_is_401(static_token) -> None:
    with pytest.raises(HTTPException) as exc:
        _verify_internal_token("")
    assert exc.value.status_code == 401


def test_internal_token_wrong_value_is_403(static_token) -> None:
    with pytest.raises(HTTPException) as exc:
        _verify_internal_token("other")
    assert exc.value.status_code == 403


def test_internal_token_not_configured_is_refused(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_TOKEN_MODE", "static")
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        _verify_internal_token("anything")
    assert exc.value.status_code == 403
