from __future__ import annotations

import hmac
import os
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

from app.core.settings import get_settings
from app.core.internal_token import (
    parse_keyring,
    sign_internal_token,
    verify_internal_token,
    InternalTokenError,
)

settings = get_settings()

# ============================================================
# Token builders (OUTBOUND)
# ============================================================

def _first_key(keys_csv: str) -> Optional[Tuple[str, str]]:
    ring = parse_keyring(keys_csv)
    for kid, secret in ring.items():
        return kid, secret
    return None


def build_internal_token() -> Optional[str]:
    """
    Build an internal token for service-to-service calls.

    Modes:
    - static : returns INTERNAL_TOKEN
    - hmac   : returns short-lived signed token
    """
    # Settings fields are snake_case (dataclass)
    mode = (getattr(settings, "internal_token_mode", "hmac") or "hmac").lower()

    # 🔥 CONFIG GUARD — prevent ambiguous setup
    if mode == "hmac" and getattr(settings, "internal_token", None):
        raise RuntimeError(
            "Misconfiguration: INTERNAL_TOKEN must not be set when INTERNAL_TOKEN_MODE=hmac"
        )

    if mode == "static":
        tok = getattr(settings, "internal_token", "")
        return tok or None

    keys_csv = getattr(settings, "internal_token_keys", "") or ""
    first = _first_key(keys_csv)
    if not first:
        return None

    kid, secret = first
    ttl = int(getattr(settings, "internal_token_ttl_sec", 300))

    return sign_internal_token(
        kid=kid,
        secret=secret,
        ttl_sec=ttl,
    )


def build_internal_headers() -> Dict[str, str]:
    tok = build_internal_token()
    headers: Dict[str, str] = {"X-Internal-Token": tok} if tok else {}
    service_token = (os.getenv("SERVICE_TOKEN", "") or "").strip()
    if service_token:
        headers["X-Service-Token"] = service_token
    return headers


# ============================================================
# FastAPI dependency (INBOUND)
# ============================================================

def require_internal_token(request: Request) -> None:
    """
    FastAPI dependency to protect internal endpoints.

    SECURITY:
    - static mode → strict equality check
    - hmac mode   → signed, time-bound token
    - fail-fast on misconfiguration
    """
    token = request.headers.get("X-Internal-Token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHENTICATED",
                "message": "Missing internal token",
                "details": {},
            },
        )

    mode = (getattr(settings, "internal_token_mode", "hmac") or "hmac").lower()

    # 🔥 CONFIG GUARD — same protection inbound
    if mode == "hmac" and getattr(settings, "internal_token", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "Server misconfiguration: INTERNAL_TOKEN must not be set in hmac mode",
                "details": {},
            },
        )

    # --------------------------------------------------------
    # STATIC MODE
    # --------------------------------------------------------
    if mode == "static":
        expected = getattr(settings, "internal_token", None)
        if not expected or not hmac.compare_digest(str(token), str(expected)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": "Invalid internal token (static)",
                    "details": {},
                },
            )
        return

    # --------------------------------------------------------
    # HMAC MODE
    # --------------------------------------------------------
    keys_csv = getattr(settings, "internal_token_keys", "") or ""
    keyring = parse_keyring(keys_csv)
    ttl = int(getattr(settings, "internal_token_ttl_sec", 300))

    try:
        verify_internal_token(
            token=token,
            keyring=keyring,
            ttl_sec=ttl,
        )
    except InternalTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Invalid internal token",
                "details": {},
            },
        )
