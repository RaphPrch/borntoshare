from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from app.governance.core.internal_token import InternalTokenError, parse_keyring, verify_internal_token
from app.governance.core.logging import get_logger
from app.governance.core.settings import get_settings
from app.governance.schemas.api_envelopes import error_payload


settings = get_settings()
logger = get_logger(__name__)
_keyring = parse_keyring(getattr(settings, "internal_token_keys", ""))


def _deny(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=error_payload(code=code, message=message))


async def require_internal_token(request: Request) -> None:
    """Router-level guard for every governance route.

    SECURITY MODEL
    - Deny by default: require a short-lived internal token
    - B2S_ALLOW_PUBLIC_API opens the non-/internal routes to the frontend BFF
    - Token mode:
        * hmac  : v1.<kid>.<exp>.<sig> (HMAC-SHA256), rotation via INTERNAL_TOKEN_KEYS
        * static: compare X-Internal-Token with INTERNAL_TOKEN (dev only)
    """
    if getattr(settings, "allow_public_api", False) and "/internal/" not in request.url.path:
        return

    mode = (getattr(settings, "internal_token_mode", "hmac") or "hmac").strip().lower()
    provided = request.headers.get("X-Internal-Token")
    is_dev = (getattr(settings, "env", "dev") or "dev").lower() == "dev"

    if mode == "static":
        expected = getattr(settings, "internal_token", "")
        if not is_dev or not expected:
            # static tokens are only allowed in dev/test
            raise _deny(503, "SERVICE_UNAVAILABLE", "Service unavailable")
        if not provided or not hmac.compare_digest(provided, expected):
            raise _deny(403, "FORBIDDEN", "Forbidden")
        return

    # HMAC mode (rotation + TTL)
    if not _keyring:
        logger.critical("[SECURITY] INTERNAL_TOKEN_KEYS not configured")
        raise _deny(503, "SERVICE_UNAVAILABLE", "Service unavailable")

    ttl = int(getattr(settings, "internal_token_ttl_sec", 300))
    try:
        kid, exp = verify_internal_token(provided or "", _keyring, ttl_sec=ttl)
    except InternalTokenError:
        # Do not leak details to client
        raise _deny(403, "FORBIDDEN", "Forbidden")
    except (TypeError, ValueError):
        logger.warning("[SECURITY] malformed internal token settings or ttl")
        raise _deny(403, "FORBIDDEN", "Forbidden")

    # Optional: attach context (useful for logs)
    request.state.internal_kid = kid
    request.state.internal_exp = exp
