from __future__ import annotations

import os
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.logging import get_logger, log_event


logger = get_logger("dal.internal_auth")


def _parse_scopes(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    return {
        part.strip().lower()
        for part in str(raw).split(",")
        if part and str(part).strip()
    }


def _validate_service_token(x_service_token: str, x_internal_token: str) -> None:
    expected = (os.getenv("SERVICE_TOKEN", "") or "").strip()
    provided_service = x_service_token if isinstance(x_service_token, str) else ""
    provided_internal = x_internal_token if isinstance(x_internal_token, str) else ""
    provided_service = provided_service.strip()
    provided_internal = provided_internal.strip()

    if expected:
        if provided_service == expected:
            return
        log_event(
            logger,
            30,
            "DAL_INTERNAL_AUTH_INVALID_SERVICE_TOKEN",
            action="validate_service_token",
            outcome="forbidden",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "INVALID_SERVICE_TOKEN",
                "message": "invalid service token",
            },
        )

    log_event(
        logger,
        30,
        "DAL_INTERNAL_AUTH_SERVICE_TOKEN_NOT_CONFIGURED",
        action="validate_service_token",
        outcome="forbidden",
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error_code": "INVALID_SERVICE_TOKEN",
            "message": "invalid service token",
        },
    )


def require_service_token(
    x_service_token: str = Header(default=""),
    x_internal_token: str = Header(default=""),
):
    _validate_service_token(x_service_token=x_service_token, x_internal_token=x_internal_token)


def require_internal(scopes: set[str]) -> Callable:
    required = {str(s).strip().lower() for s in (scopes or set()) if str(s).strip()}

    def _dep(
        request: Request,
        x_service_token: str = Header(default=""),
        x_internal_token: str = Header(default=""),
        x_service_name: str = Header(default=""),
        x_service_scope: str = Header(default=""),
    ) -> None:
        _validate_service_token(x_service_token=x_service_token, x_internal_token=x_internal_token)

        service_name = str(x_service_name or "").strip().lower()
        if not service_name:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "MISSING_SERVICE_NAME",
                    "message": "missing X-Service-Name",
                },
            )

        provided_scopes = _parse_scopes(x_service_scope)
        missing = sorted(s for s in required if s not in provided_scopes)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "MISSING_REQUIRED_SCOPES",
                    "message": f"missing required scope(s): {', '.join(missing)}",
                    "details": {"missing_scopes": missing},
                },
            )

        correlation_id = (
            request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or ""
        )
        log_event(
            logger,
            20,
            "DAL_INTERNAL_AUTH_OK",
            action="validate_internal_headers",
            target=service_name,
            outcome="success",
            request_id=correlation_id,
            details={"required_scopes": sorted(required)},
        )

    return Depends(_dep)
