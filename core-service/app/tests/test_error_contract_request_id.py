from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from fastapi.testclient import TestClient

from app.core.errors import ensure_request_id, register_exception_handlers
from app.core.logging import clear_request_id_context, get_logger, set_request_id_context


class _Color(BaseModel):
    color: str

    @field_validator("color")
    @classmethod
    def _hex(cls, value: str) -> str:
        if not value.startswith("#"):
            raise ValueError("A color like #2563eb is expected")
        return value


def _new_client(*, raise_server_exceptions: bool = True) -> TestClient:
    app = FastAPI()
    logger = get_logger("core.tests.error_contract")

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next):
        request_id = ensure_request_id(request)
        set_request_id_context(request_id)
        try:
            response = await call_next(request)
        finally:
            clear_request_id_context()
        response.headers["X-Request-ID"] = request_id
        return response

    register_exception_handlers(app, logger)

    @app.get("/http")
    def _http_error() -> dict[str, bool]:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "RESOURCE_NOT_FOUND",
                "message": "resource missing",
                "entity": "identity",
            },
        )

    @app.get("/validate")
    def _validate(limit: int = Query(..., ge=1)) -> dict[str, int]:
        return {"limit": limit}

    @app.post("/color")
    def _color(payload: _Color) -> dict[str, str]:
        return {"color": payload.color}

    @app.get("/panic")
    def _panic() -> dict[str, bool]:
        raise RuntimeError("boom")

    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_http_exception_returns_normalized_error_and_request_id() -> None:
    with _new_client() as client:
        res = client.get("/http", headers={"X-Request-ID": "rid-http-1"})

    assert res.status_code == 404
    assert res.headers.get("X-Request-ID") == "rid-http-1"
    body = res.json()
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert body["error"]["message"] == "resource missing"
    assert body["error"]["details"] == {"entity": "identity"}
    assert body["error"]["request_id"] == "rid-http-1"


def test_validation_error_has_standard_contract() -> None:
    with _new_client() as client:
        res = client.get("/validate", headers={"X-Request-ID": "rid-val-1"})

    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    # The message of the failed field (here the missing query parameter)
    assert body["error"]["message"] == "Field required"
    assert isinstance(body["error"]["details"], dict)
    assert isinstance(body["error"]["details"].get("errors"), list)
    assert body["error"]["request_id"] == "rid-val-1"
    assert res.headers.get("X-Request-ID") == "rid-val-1"


def test_unhandled_exception_maps_to_internal_error_contract() -> None:
    with _new_client(raise_server_exceptions=False) as client:
        res = client.get("/panic", headers={"X-Request-ID": "rid-panic-1"})

    assert res.status_code == 500
    body = res.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "Internal server error."
    assert body["error"]["details"] == {}
    assert body["error"]["request_id"] == "rid-panic-1"
    assert res.headers.get("X-Request-ID") == "rid-panic-1"


def test_request_id_is_generated_when_header_absent() -> None:
    with _new_client() as client:
        res = client.get("/http")

    assert res.status_code == 404
    rid = res.headers.get("X-Request-ID")
    assert isinstance(rid, str)
    assert len(rid or "") >= 8
    assert res.json()["error"]["request_id"] == rid



def test_a_validator_error_is_a_422_with_its_message() -> None:
    with _new_client() as client:
        res = client.post("/color", json={"color": "red"})

    assert res.status_code == 422
    assert res.json()["error"]["message"] == "A color like #2563eb is expected"
