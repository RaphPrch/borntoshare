from __future__ import annotations

from fastapi import HTTPException
from starlette.requests import Request

from app.core.internal_headers import get_internal_headers


def _request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (k.lower().encode("latin-1"), str(v).encode("latin-1"))
            for k, v in headers.items()
        ],
    }
    return Request(scope)


def test_get_internal_headers_requires_internal_token() -> None:
    req = _request({})
    try:
        get_internal_headers(req)
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        detail = exc.detail
        assert isinstance(detail, dict)
        assert detail.get("error_code") == "MISSING_INTERNAL_TOKEN"


def test_get_internal_headers_propagates_supported_headers() -> None:
    req = _request(
        {
            "X-Internal-Token": "tok-1",
            "X-Request-ID": "rid-1",
            "X-Service-Name": "frontend-service",
            "X-Service-Scope": "read:identity",
            "X-Service-Token": "svc-1",
            "X-Ignored": "noop",
        }
    )
    headers = get_internal_headers(req)

    assert headers["accept"] == "application/json"
    assert headers["X-Internal-Token"] == "tok-1"
    assert headers["X-Request-ID"] == "rid-1"
    assert headers["X-Service-Name"] == "frontend-service"
    assert headers["X-Service-Scope"] == "read:identity"
    assert headers["X-Service-Token"] == "svc-1"
    assert "X-Ignored" not in headers
