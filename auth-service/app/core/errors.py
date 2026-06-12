from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import log_event


def get_request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


def ensure_request_id(request: Request) -> str:
    existing = (request.headers.get("X-Request-ID") or "").strip()
    request_id = existing or str(uuid.uuid4())
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
    if status_code >= 500:
        return "Internal server error."
    return "Request failed."


def _normalize_http_error_detail(
    detail: Any,
    *,
    status_code: int,
) -> tuple[str, str, dict[str, Any]]:
    if isinstance(detail, dict):
        explicit_code = str(detail.get("code") or "").strip() or _error_code_from_status(status_code)
        message = str(
            detail.get("message")
            or detail.get("detail")
            or _default_message(status_code)
        )
        details = detail.get("details")
        if isinstance(details, dict):
            details_obj = details
        else:
            details_obj = {}
        return explicit_code, message, details_obj

    if isinstance(detail, list):
        return (
            _error_code_from_status(status_code),
            _default_message(status_code),
            {"items": detail},
        )

    if detail is None:
        return _error_code_from_status(status_code), _default_message(status_code), {}

    message = str(detail).strip() or _default_message(status_code)
    return _error_code_from_status(status_code), message, {}


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            }
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


def register_exception_handlers(app: FastAPI, logger: logging.Logger) -> None:
    @app.exception_handler(HTTPException)
    async def _http_exc_handler(request: Request, exc: HTTPException):
        request_id = get_request_id(request) or ensure_request_id(request)
        code, message, details = _normalize_http_error_detail(exc.detail, status_code=exc.status_code)
        level = logging.WARNING if 400 <= exc.status_code < 500 else logging.ERROR
        log_event(
            logger,
            level,
            "AUTH_HTTP_EXCEPTION",
            service="auth-service",
            module="runtime",
            action="http_exception",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=exc.status_code,
            error_code=code,
            message=message,
        )
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        request_id = get_request_id(request) or ensure_request_id(request)
        details = {"errors": exc.errors()}
        log_event(
            logger,
            logging.WARNING,
            "AUTH_REQUEST_VALIDATION_ERROR",
            service="auth-service",
            module="runtime",
            action="validation_error",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=422,
            error_code="VALIDATION_ERROR",
            details_count=len(details["errors"]),
        )
        return _error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Validation failed.",
            details=details,
            request_id=request_id,
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        request_id = get_request_id(request) or ensure_request_id(request)
        log_event(
            logger,
            logging.ERROR,
            "AUTH_UNHANDLED_EXCEPTION",
            service="auth-service",
            module="runtime",
            action="unhandled_exception",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=500,
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        logger.exception("AUTH_UNHANDLED_EXCEPTION_TRACE", exc_info=exc)
        return _error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Internal server error.",
            details={},
            request_id=request_id,
        )
