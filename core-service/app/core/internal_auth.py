"""Service-to-service authentication (inbound checks).

- X-Internal-Token: static (INTERNAL_TOKEN) or short-lived HMAC token (INTERNAL_TOKEN_KEYS), see internal_token.py
- X-Service-Token: shared SERVICE_TOKEN, plus X-Service-Name / X-Service-Scope for scoped internal routes
"""
from __future__ import annotations

import hmac
import os
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import get_settings
from app.core.internal_token import InternalTokenError, parse_keyring, verify_internal_token
from app.core.logging import get_logger, log_event


logger = get_logger("core.internal_auth")


def _token_mode() -> str:
    return os.getenv("INTERNAL_TOKEN_MODE", "hmac").strip().lower()


def _token_ttl() -> int:
    return int(os.getenv("INTERNAL_TOKEN_TTL_SEC", "300"))


# ============================================================
# X-Internal-Token
# ============================================================

def require_internal_token(request: Request) -> None:
    """Protect internal endpoints (static or hmac)."""
    provided = request.headers.get("X-Internal-Token")

    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing internal token",
        )

    if _token_mode() == "static":
        expected = os.getenv("INTERNAL_TOKEN", "")
        if not expected or not hmac.compare_digest(provided, expected):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid internal token",
            )
        return

    keyring = parse_keyring(os.getenv("INTERNAL_TOKEN_KEYS", ""))
    if not keyring:
        logger.critical("[SECURITY] INTERNAL_TOKEN_KEYS not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable",
        )

    try:
        kid, exp = verify_internal_token(provided, keyring, ttl_sec=_token_ttl())
    except InternalTokenError:
        # Do not leak details to client
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal token",
        )

    request.state.internal_kid = kid
    request.state.internal_exp = exp


def require_orchestration_access(request: Request) -> None:
    """Guard for the orchestration routes (/governance/*).

    B2S_ALLOW_PUBLIC_API opens the non-/internal/ ones to the frontend BFF;
    everything else requires an internal token.
    """
    if get_settings().ALLOW_PUBLIC_API and "/internal/" not in request.url.path:
        return
    require_internal_token(request)


# ============================================================
# X-Service-Token / X-Service-Name / X-Service-Scope
# ============================================================

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
    provided_service = provided_service.strip()

    if expected:
        if hmac.compare_digest(provided_service, expected):
            return
        log_event(
            logger,
            30,
            "CORE_INTERNAL_AUTH_INVALID_SERVICE_TOKEN",
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
        "CORE_INTERNAL_AUTH_SERVICE_TOKEN_NOT_CONFIGURED",
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
            "CORE_INTERNAL_AUTH_OK",
            action="validate_internal_headers",
            target=service_name,
            outcome="success",
            request_id=correlation_id,
            details={"required_scopes": sorted(required)},
        )

    return Depends(_dep)
