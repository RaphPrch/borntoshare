from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.internal_token import InternalTokenError, parse_keyring, verify_internal_token
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.schemas.api_envelopes import error_payload


settings = get_settings()
logger = get_logger(__name__)


class InternalGuardMiddleware(BaseHTTPMiddleware):
    """Global internal guard.

    SECURITY MODEL
    - Deny by default
    - Require a short-lived internal token for all endpoints except health checks
    - Token mode:
        * hmac  : v1.<kid>.<exp>.<sig> (HMAC-SHA256), rotation via INTERNAL_TOKEN_KEYS
        * static: compare X-Internal-Token with INTERNAL_TOKEN (dev only)
    """

    # Endpoints that must remain reachable without auth for orchestration
    EXEMPT_PATHS = {
        "/healthz",
        "/api/health",
        "/livez",
        "/readyz",
    }

    def __init__(self, app):
        super().__init__(app)
        self._keyring = parse_keyring(getattr(settings, "internal_token_keys", ""))

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if getattr(settings, "allow_public_api", False) and not path.startswith("/internal"):
            return await call_next(request)

        # Allow health checks
        if path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Optionally allow docs in debug
        if getattr(settings, "debug", False) and path in {"/docs", "/openapi.json", "/redoc"}:
            return await call_next(request)

        mode = (getattr(settings, "internal_token_mode", "hmac") or "hmac").strip().lower()
        provided = request.headers.get("X-Internal-Token")

        is_dev = (getattr(settings, "env", "dev") or "dev").lower() == "dev"

        if mode == "static":
            expected = getattr(settings, "internal_token", "")
            if not is_dev:
                # static tokens are only allowed in dev/test
                return JSONResponse(
                    status_code=503,
                    content=error_payload(code="SERVICE_UNAVAILABLE", message="Service unavailable"),
                )
            if not expected:
                return JSONResponse(
                    status_code=503,
                    content=error_payload(code="SERVICE_UNAVAILABLE", message="Service unavailable"),
                )
            if not provided or provided != expected:
                return JSONResponse(
                    status_code=403,
                    content=error_payload(code="FORBIDDEN", message="Forbidden"),
                )
            return await call_next(request)

        # HMAC mode (rotation + TTL)
        if not self._keyring:
            # Require key ring configured
            logger.critical("[SECURITY] INTERNAL_TOKEN_KEYS not configured")
            return JSONResponse(
                status_code=503,
                content=error_payload(code="SERVICE_UNAVAILABLE", message="Service unavailable"),
            )

        ttl = int(getattr(settings, "internal_token_ttl_sec", 300))
        try:
            kid, exp = verify_internal_token(provided or "", self._keyring, ttl_sec=ttl)
        except InternalTokenError:
            # Do not leak details to client
            return JSONResponse(
                status_code=403,
                content=error_payload(code="FORBIDDEN", message="Forbidden"),
            )
        except (TypeError, ValueError):
            logger.warning("[SECURITY] malformed internal token settings or ttl")
            return JSONResponse(
                status_code=403,
                content=error_payload(code="FORBIDDEN", message="Forbidden"),
            )

        # Optional: attach context (useful for logs)
        request.state.internal_kid = kid
        request.state.internal_exp = exp
        return await call_next(request)
