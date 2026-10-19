"""Service-to-service authentication (inbound checks).

- X-Internal-Token: static (INTERNAL_TOKEN) or short-lived HMAC token (INTERNAL_TOKEN_KEYS), see internal_token.py
- X-Service-Name / X-Service-Scope: caller identity and scopes for scoped internal routes (with X-Internal-Token)
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

def _verify_internal_token(provided: str | None) -> tuple[str, int] | None:
    """Check X-Internal-Token (static or hmac); returns (kid, exp) in hmac mode."""
    provided = str(provided or "").strip()
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
        return None

    keyring = parse_keyring(os.getenv("INTERNAL_TOKEN_KEYS", ""))
    if not keyring:
        logger.critical("[SECURITY] INTERNAL_TOKEN_KEYS not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable",
        )

    try:
        return verify_internal_token(provided, keyring, ttl_sec=_token_ttl())
    except InternalTokenError:
        # Do not leak details to client
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal token",
        )


def require_internal_token(request: Request) -> None:
    """Protect internal endpoints (static or hmac)."""
    verified = _verify_internal_token(request.headers.get("X-Internal-Token"))
    if verified:
        request.state.internal_kid, request.state.internal_exp = verified


def require_orchestration_access(request: Request) -> None:
    """Guard for the orchestration routes (/governance/*).

    B2S_ALLOW_PUBLIC_API opens the non-/internal/ ones to the frontend BFF;
    everything else requires an internal token.
    """
    if get_settings().ALLOW_PUBLIC_API and "/internal/" not in request.url.path:
        return
    require_internal_token(request)


# ============================================================
# X-Service-Name / X-Service-Scope (scoped internal routes)
# ============================================================

def _parse_scopes(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    return {
        part.strip().lower()
        for part in str(raw).split(",")
        if part and str(part).strip()
    }


def require_internal(scopes: set[str]) -> Callable:
    required = {str(s).strip().lower() for s in (scopes or set()) if str(s).strip()}

    def _dep(
        request: Request,
        x_internal_token: str = Header(default=""),
        x_service_name: str = Header(default=""),
        x_service_scope: str = Header(default=""),
    ) -> None:
        _verify_internal_token(x_internal_token)

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
