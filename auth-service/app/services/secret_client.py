from __future__ import annotations

"""Secrets of auth-service: stored and read through core-service, which holds the key."""

import os
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger, get_request_id_context, log_event
from app.core.internal_token import build_internal_headers

logger = get_logger(__name__)


class SecretStoreUnavailable(RuntimeError):
    pass


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def _call_core(path: str, payload: dict[str, str]) -> dict:
    settings = get_settings()
    url = settings.CORE_URL.rstrip("/") + path
    headers = {"accept": "application/json", "content-type": "application/json", **build_internal_headers()}
    request_id = (get_request_id_context() or "").strip()
    if request_id:
        headers["X-Request-ID"] = request_id
    try:
        with httpx.Client(timeout=getattr(settings, "CORE_TIMEOUT_SECONDS", 5)) as client:
            res = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        log_event(logger, 40, "AUTH_SECRET_CALL_FAILED", provider="core", target=path, outcome="http_error", message=str(exc))
        raise SecretStoreUnavailable(f"core-service unreachable: {exc}") from exc
    try:
        body = res.json() if res.content else {}
    except ValueError as exc:
        raise SecretStoreUnavailable("core-service returned invalid JSON") from exc
    if res.status_code != 200:
        detail = body.get("detail") or body.get("error") if isinstance(body, dict) else None
        code = detail.get("code") if isinstance(detail, dict) else "SECRET_PROVIDER_FAILURE"
        message = detail.get("message") if isinstance(detail, dict) else f"HTTP {res.status_code}"
        raise SecretStoreUnavailable(f"{code}: {message}")
    return body.get("data") if isinstance(body.get("data"), dict) else {}


def resolve_secret(ref: str, *, default: Optional[str] = None) -> str:
    """Value of a reference: env://VAR, file:///path or sm://...; default (or "") when it cannot be read."""
    if not ref:
        return default or ""
    ref = str(ref).strip()

    if ref.startswith("env://"):
        return os.getenv(ref[len("env://"):], default or "")

    if ref.startswith("file://"):
        try:
            return _read_file(ref[len("file://"):])
        except OSError:
            return default or ""

    if ref.startswith("sm://"):
        try:
            value = _call_core("/api/internal/secrets/resolve", {"ref": ref}).get("value")
            if value is None:
                raise SecretStoreUnavailable("core-service returned no value")
            return str(value)
        except RuntimeError:
            if default is not None:
                return default
            raise

    if default is not None:
        return default
    raise RuntimeError("Unsupported secret ref")


def store_secret(name: str, value: str) -> str:
    """Store a value and return its reference (sm://...), which is what the callers keep. The value is never returned."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Secret name is required")
    if not value:
        raise ValueError("Secret value is required")
    ref = str(_call_core("/api/internal/secrets/store", {"name": name, "value": value}).get("ref") or "").strip()
    if not ref:
        raise SecretStoreUnavailable("core-service returned an empty reference")
    return ref
