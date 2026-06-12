from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.api_envelopes import error_payload


def get_request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


def ensure_request_id(request: Request) -> str:
    existing = str(request.headers.get("x-request-id") or "").strip()
    request_id = existing or f"req_{uuid.uuid4().hex}"
    request.state.request_id = request_id
    return request_id


def _error_code_from_status(status_code: int) -> str:
    if status_code == 400:
        return "BAD_REQUEST"
    if status_code == 401:
        return "UNAUTHENTICATED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 422:
        return "VALIDATION_ERROR"
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "HTTP_ERROR"


def _default_message(status_code: int) -> str:
    if status_code == 400:
        return "Bad request."
    if status_code == 401:
        return "Authentication required."
    if status_code == 403:
        return "Forbidden."
    if status_code == 404:
        return "Resource not found."
    if status_code == 422:
        return "Validation failed."
    if status_code >= 500:
        return "Internal server error."
    return "Request failed."


def _normalize_http_detail(detail: Any, *, status_code: int) -> tuple[str, str, dict[str, Any]]:
    if isinstance(detail, dict) and detail.get("ok") is False and isinstance(detail.get("error"), dict):
        nested = dict(detail.get("error") or {})
        code = str(nested.get("code") or _error_code_from_status(status_code)).strip()
        message = str(nested.get("message") or _default_message(status_code))
        details = dict(nested.get("details") or {}) if isinstance(nested.get("details"), dict) else {}
        return code, message, details

    if isinstance(detail, dict):
        if isinstance(detail.get("error"), dict):
            nested = dict(detail.get("error") or {})
            code = str(nested.get("code") or nested.get("error_code") or _error_code_from_status(status_code)).strip()
            message = str(nested.get("message") or nested.get("detail") or _default_message(status_code))
            if isinstance(nested.get("details"), dict):
                details = dict(nested.get("details") or {})
            else:
                details = {
                    k: v
                    for k, v in nested.items()
                    if k not in {"code", "error_code", "message", "detail", "request_id", "details"}
                }
            return code, message, details

        code = str(detail.get("code") or detail.get("error_code") or _error_code_from_status(status_code)).strip()
        message = str(detail.get("message") or detail.get("detail") or _default_message(status_code))
        details = {
            k: v
            for k, v in detail.items()
            if k not in {"code", "error_code", "message", "detail", "request_id"}
        }
        return code, message, details

    if isinstance(detail, list):
        return _error_code_from_status(status_code), _default_message(status_code), {"items": detail}

    if detail is None:
        return _error_code_from_status(status_code), _default_message(status_code), {}

    return _error_code_from_status(status_code), str(detail).strip() or _default_message(status_code), {}


def json_error_response(
    *,
    status_code: int,
    request_id: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content=error_payload(
            code=code,
            message=message,
            request_id=request_id,
            extra=details or {},
        ),
    )
    response.headers["x-request-id"] = request_id
    return response


def register_exception_handlers(app: FastAPI, logger: logging.Logger) -> None:
    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        request_id = get_request_id(request) or ensure_request_id(request)
        code, message, details = _normalize_http_detail(exc.detail, status_code=exc.status_code)
        level = logging.WARNING if 400 <= exc.status_code < 500 else logging.ERROR
        logger.log(
            level,
            "governance.http_exception method=%s path=%s status=%s code=%s request_id=%s",
            request.method,
            request.url.path,
            exc.status_code,
            code,
            request_id,
        )
        return json_error_response(
            status_code=exc.status_code,
            request_id=request_id,
            code=code,
            message=message,
            details=details,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = get_request_id(request) or ensure_request_id(request)
        logger.warning(
            "governance.validation_error method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            request_id,
        )
        return json_error_response(
            status_code=422,
            request_id=request_id,
            code="VALIDATION_ERROR",
            message="Validation failed.",
            details={"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        request_id = get_request_id(request) or ensure_request_id(request)
        logger.exception(
            "governance.unhandled_exception method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            request_id,
            exc_info=exc,
        )
        return json_error_response(
            status_code=500,
            request_id=request_id,
            code="INTERNAL_ERROR",
            message="Internal server error.",
            details={},
        )
