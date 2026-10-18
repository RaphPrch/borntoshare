from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.schemas.auth import UserInfo

settings = get_settings()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _principal_exp(ttl_seconds: int | None = None) -> int:
    ttl = int(ttl_seconds or settings.PRINCIPAL_TTL_SECONDS)
    now = datetime.now(timezone.utc)
    return int((now + timedelta(seconds=max(1, ttl))).timestamp())


def principal_payload_from_user(user: UserInfo, ttl_seconds: int | None = None) -> dict:
    identity_id = str(user.identity_id or "").strip()
    if not identity_id:
        raise ValueError("identity_id is required for principal snapshot")

    try:
        subject_id = int(identity_id)
    except Exception as exc:
        raise ValueError("identity_id must be an integer-compatible value") from exc

    roles = [str(r) for r in (user.roles or [])]
    normalized_roles = {role.strip().lower() for role in roles}
    return {
        "id": subject_id,
        "username": str(user.username),
        "display_name": user.display_name,
        "email": user.email,
        "roles": roles,
        "is_admin": "platform_admin" in normalized_roles or "admin" in normalized_roles,
        "ver": 1,
        "exp": _principal_exp(ttl_seconds),
    }


def sign_principal_payload(payload: dict) -> str:
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    sig = hmac.new(
        settings.PRINCIPAL_SIGNING_KEY.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{payload_b64}.{sig_b64}"


def issue_principal_snapshot_cookie_value(user: UserInfo, ttl_seconds: int | None = None) -> str:
    payload = principal_payload_from_user(user, ttl_seconds=ttl_seconds)
    return sign_principal_payload(payload)
