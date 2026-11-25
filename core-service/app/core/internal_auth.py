"""Service-to-service authentication (inbound checks).

- X-Service-Token: the token of the calling service, which names it (app.core.service_identity); its scopes are
  set by core-service
- before make deploy gave these tokens (« legacy »): X-Internal-Token, the token shared by every service, and
  X-Service-Name / X-Service-Scope as the caller declares them
"""
from __future__ import annotations

import hmac
import os
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.logging import get_logger, log_event


logger = get_logger("core.internal_auth")


# ============================================================
# X-Internal-Token
# ============================================================

def _verify_internal_token(provided: str | None) -> None:
    """Check X-Internal-Token against INTERNAL_TOKEN (constant-time comparison)."""
    provided = str(provided or "").strip()
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing internal token",
        )
    expected = os.getenv("INTERNAL_TOKEN", "")
    if not expected or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal token",
        )


def internal_caller(request: Request) -> str | None:
    """The calling service (frontend, auth, capsule, fives, or « legacy »), None for an unknown token."""
    from app.core.service_identity import TOKEN_HEADER, caller_of

    return caller_of(request.headers.get(TOKEN_HEADER), request.headers.get("X-Internal-Token"))


def require_internal_token(request: Request) -> None:
    """Protect internal endpoints: a service, never the BFF acting for a person."""
    from app.core.service_identity import INTERNAL_CALLERS, per_service_mode

    if not per_service_mode():
        _verify_internal_token(request.headers.get("X-Internal-Token"))
        return
    caller = internal_caller(request)
    if caller is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing internal token")
    if caller not in INTERNAL_CALLERS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal route: not for the web interface")


def require_orchestration_access(request: Request) -> None:
    """Guard for the orchestration routes (/governance/*): a known caller, the BFF included (it calls them for a
    person, whose rights each route checks)."""
    from app.core.service_identity import per_service_mode

    if not per_service_mode():
        require_internal_token(request)
        return
    if internal_caller(request) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing internal token")


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
        from app.core.service_identity import SCOPES, per_service_mode

        if per_service_mode():
            # The caller is the owner of its token, its scopes are those core-service gives it
            caller = internal_caller(request)
            if caller is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing internal token")
            granted = SCOPES.get(caller, frozenset())
            missing = sorted(s for s in required if s not in granted)
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error_code": "MISSING_REQUIRED_SCOPES", "message": f"missing required scope(s): {', '.join(missing)}",
                            "details": {"missing_scopes": missing, "service": caller}},
                )
            return

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
