from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Dict, Tuple


TOKEN_PREFIX = "v1"


class InternalTokenError(Exception):
    """Raised when an internal token is invalid or expired."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:  # pragma: no cover
        return self.message


# ============================================================
# Base64 helpers (URL-safe, no padding)
# ============================================================

def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


# ============================================================
# Keyring
# ============================================================

def parse_keyring(keys_csv: str) -> Dict[str, str]:
    """
    Parse key ring from CSV:
      "kid1:secret1,kid2:secret2"
    """
    out: Dict[str, str] = {}
    for part in (keys_csv or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue

        kid, secret = part.split(":", 1)
        kid = kid.strip()
        secret = secret.strip()

        if kid and secret:
            out[kid] = secret

    return out


# ============================================================
# Sign / Verify
# ============================================================

def sign_internal_token(kid: str, secret: str, ttl_sec: int) -> str:
    """
    Generate a short-lived internal token.

    Format:
      v1.<kid>.<exp_unix>.<sig>

    sig = b64url(HMAC-SHA256(secret, "v1.<kid>.<exp>"))
    """
    now = int(time.time())
    exp = now + int(ttl_sec)

    msg = f"{TOKEN_PREFIX}.{kid}.{exp}".encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    sig = _b64url_encode(mac)

    return f"{TOKEN_PREFIX}.{kid}.{exp}.{sig}"


def verify_internal_token(
    token: str,
    keyring: Dict[str, str],
    ttl_sec: int,
    leeway_sec: int = 30,
) -> Tuple[str, int]:
    """
    Verify token signature and expiry.

    Returns:
      (kid, exp)

    Raises:
      InternalTokenError
    """
    if not token:
        raise InternalTokenError("missing token")

    parts = token.split(".")
    if len(parts) != 4:
        raise InternalTokenError("bad token format")

    prefix, kid, exp_s, sig = parts

    if prefix != TOKEN_PREFIX:
        raise InternalTokenError("bad token version")

    if kid not in keyring:
        raise InternalTokenError("unknown kid")

    try:
        exp = int(exp_s)
    except ValueError:
        raise InternalTokenError("bad exp")

    now = int(time.time())

    # Expired (with leeway)
    if now > exp + int(leeway_sec):
        raise InternalTokenError("token expired")

    # Too far in the future (replay / abuse protection)
    if exp > now + int(ttl_sec) + int(leeway_sec):
        raise InternalTokenError("exp too far")

    msg = f"{TOKEN_PREFIX}.{kid}.{exp}".encode("utf-8")
    secret = keyring[kid]
    mac = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    expected_sig = _b64url_encode(mac)

    # Constant-time comparison
    if not hmac.compare_digest(expected_sig, sig):
        raise InternalTokenError("bad signature")

    return kid, exp
