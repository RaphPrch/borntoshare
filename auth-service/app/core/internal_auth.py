from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.core.config import get_settings
from app.core.internal_token import (
    parse_keyring,
    sign_internal_token,
)

settings = get_settings()

# ============================================================
# INTERNAL TOKEN (CLIENT SIDE / OUTBOUND)
# ============================================================


def _first_key(keys_csv: str) -> Optional[Tuple[str, str]]:
    """
    Return first (kid, secret) from INTERNAL_TOKEN_KEYS.
    Used for signing short-lived HMAC tokens.
    """
    ring = parse_keyring(keys_csv)
    for kid, secret in ring.items():
        return kid, secret
    return None


def build_internal_token() -> Optional[str]:
    """
    Build an internal token for service-to-service calls.

    Modes (via env):
    - INTERNAL_TOKEN_MODE=static
        → use INTERNAL_TOKEN as-is (dev / bootstrap)
    - INTERNAL_TOKEN_MODE=hmac (default)
        → sign short-lived token using INTERNAL_TOKEN_KEYS
    """
    mode = (getattr(settings, "INTERNAL_TOKEN_MODE", "hmac") or "hmac").lower()

    # --------------------------------------------------------
    # STATIC TOKEN (dev / bootstrap only)
    # --------------------------------------------------------
    if mode == "static":
        token = getattr(settings, "INTERNAL_TOKEN", None)
        return token or None

    # --------------------------------------------------------
    # HMAC TOKEN (recommended / prod)
    # --------------------------------------------------------
    keys_csv = getattr(settings, "INTERNAL_TOKEN_KEYS", "") or ""
    first = _first_key(keys_csv)
    if not first:
        return None

    kid, secret = first
    ttl = int(getattr(settings, "INTERNAL_TOKEN_TTL_SEC", 300))

    return sign_internal_token(
        kid=kid,
        secret=secret,
        ttl_sec=ttl,
    )


def build_internal_headers() -> Dict[str, str]:
    """
    Build headers for internal service-to-service HTTP calls.
    """
    token = build_internal_token()
    if not token:
        return {}

    return {
        "X-Internal-Token": token,
    }
