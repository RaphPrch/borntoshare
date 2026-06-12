from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Iterable

import httpx

from app.core.logging import get_request_id_context, get_logger, log_event


BROKER_URL = os.getenv("B2S_SECRET_BROKER_URL", "http://secret-broker:8010").rstrip("/")
DEFAULT_MODE = os.getenv("B2S_SECRETS_MODE", "refs").strip().lower()  # refs|none
DEFAULT_TTL = int(os.getenv("B2S_SECRETS_TTL_SECONDS", "60"))
PROVIDER_FILTER = os.getenv("SECRET_REF_PROVIDER", "").strip().lower()
logger = get_logger(__name__)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


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


def _build_internal_token() -> str | None:
    mode = os.getenv("INTERNAL_TOKEN_MODE", "hmac").strip().lower()
    if mode == "static":
        return os.getenv("INTERNAL_TOKEN") or None

    keyring = _parse_keyring(os.getenv("INTERNAL_TOKEN_KEYS", ""))
    if not keyring:
        return None

    kid, secret = next(iter(keyring.items()))
    ttl = int(os.getenv("INTERNAL_TOKEN_TTL_SEC", "300"))
    now = int(time.time())
    exp = now + ttl
    msg = f"v1.{kid}.{exp}".encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    sig = _b64url_encode(mac)
    return f"v1.{kid}.{exp}.{sig}"


def _allowed_prefixes() -> set[str]:
    if not PROVIDER_FILTER:
        return set()
    tokens = [t.strip() for t in PROVIDER_FILTER.split(",") if t.strip()]
    mapping = {
        "env": "env://",
        "file": "file://",
        "vault": "vault://",
        "aws": "aws-sm://",
        "azure": "kv://",
    }
    prefixes: set[str] = set()
    for token in tokens:
        if "://" in token:
            prefixes.add(token)
        elif token in mapping:
            prefixes.add(mapping[token])
    return prefixes


def _validate_ref(secret_ref: str) -> None:
    allowed = _allowed_prefixes()
    if allowed and not any(secret_ref.startswith(prefix) for prefix in allowed):
        raise ValueError("Secret ref provider not allowed by SECRET_REF_PROVIDER")


def resolve_secret_ref(secret_ref: str, ttl_seconds: int | None = None) -> str:
    _validate_ref(secret_ref)
    mode = DEFAULT_MODE
    if mode == "none":
        return ""

    token = _build_internal_token()
    if not token:
        raise RuntimeError("Missing internal token configuration for secret broker")

    ttl = ttl_seconds or DEFAULT_TTL
    headers = {"X-Internal-Token": token}
    request_id = (get_request_id_context() or "").strip()
    if request_id:
        headers["X-Request-ID"] = request_id

    log_event(
        logger,
        logging.DEBUG,
        "DAL_SECRET_RESOLVE_ATTEMPT",
        action="secret_resolve",
        target=secret_ref,
        outcome="attempt",
    )
    with httpx.Client(timeout=5.0) as client:
        res = client.post(
            f"{BROKER_URL}/resolve",
            json={"ref": secret_ref, "ttl_seconds": ttl, "mode": mode},
            headers=headers,
        )
    if res.status_code != 200:
        log_event(
            logger,
            logging.ERROR,
            "DAL_SECRET_RESOLVE_FAILED",
            action="secret_resolve",
            target=secret_ref,
            outcome="broker_error",
            status_code=res.status_code,
        )
        raise RuntimeError(f"Secret broker error for {secret_ref}: {res.text}")
    data = res.json()
    if data.get("mode") == "token":
        raise RuntimeError("Secret broker returned token mode; value not available in DAL")
    log_event(
        logger,
        logging.DEBUG,
        "DAL_SECRET_RESOLVE_SUCCESS",
        action="secret_resolve",
        target=secret_ref,
        outcome="success",
    )
    return data.get("value") or ""
