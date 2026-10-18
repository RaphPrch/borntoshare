from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

from app.governance.core.settings import get_settings
from app.governance.core.internal_token import (
    parse_keyring,
    sign_internal_token,
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
