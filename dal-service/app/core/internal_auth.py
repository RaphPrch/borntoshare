from __future__ import annotations

import os
import base64
import hashlib
import hmac
import time
from fastapi import HTTPException, Request, status


def _parse_keyring(keys_csv: str) -> dict[str, str]:
    out: dict[str, str] = {}
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


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _verify_internal_token(token: str, keyring: dict[str, str], ttl_sec: int, leeway_sec: int = 30) -> None:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing internal token")

    parts = token.split(".")
    if len(parts) != 4:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")

    prefix, kid, exp_s, sig = parts
    if prefix != "v1":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")

    if kid not in keyring:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")

    try:
        exp = int(exp_s)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")

    now = int(time.time())
    if now > exp + int(leeway_sec):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")
    if exp > now + int(ttl_sec) + int(leeway_sec):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")

    msg = f"v1.{kid}.{exp}".encode("utf-8")
    secret = keyring[kid]
    mac = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    expected_sig = _b64url_encode(mac)
    if not hmac.compare_digest(expected_sig, sig):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")


def require_internal_token(request: Request) -> None:
    """
    Protect DAL internal endpoints (production-ready; static or hmac).
    """
    mode = os.getenv("INTERNAL_TOKEN_MODE", "hmac").strip().lower()
    provided = request.headers.get("X-Internal-Token")

    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing internal token",
        )

    if mode == "static":
        expected = os.getenv("INTERNAL_TOKEN", "")
        if not expected or provided != expected:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid internal token",
            )
        return

    keys_csv = os.getenv("INTERNAL_TOKEN_KEYS", "")
    keyring = _parse_keyring(keys_csv)
    if not keyring:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable",
        )

    ttl = int(os.getenv("INTERNAL_TOKEN_TTL_SEC", "300"))
    _verify_internal_token(provided, keyring, ttl_sec=ttl)
