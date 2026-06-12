from __future__ import annotations

"""Secret resolution and storage helpers."""

import httpx
import os
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger, get_request_id_context, log_event

logger = get_logger(__name__)


# ==================================================
# 🔐 Helpers
# ==================================================

def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def _secret_broker_url() -> str:
    settings = get_settings()
    return (
        getattr(settings, "B2S_SECRET_BROKER_URL", None)
        or "http://secret-broker:8010"
    ).strip().rstrip("/")


def _secret_broker_timeout() -> float:
    settings = get_settings()
    raw = str(getattr(settings, "B2S_SECRET_BROKER_TIMEOUT_SECONDS", 5)).strip()
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 5.0


def _secret_write_token() -> str | None:
    settings = get_settings()
    tok = getattr(settings, "B2S_SECRET_WRITE_TOKEN", None)
    tok = (tok or "").strip()
    return tok or None


def _internal_token() -> str:
    settings = get_settings()
    tok = (getattr(settings, "INTERNAL_TOKEN", None) or "").strip()
    if not tok:
        raise SecretStoreUnavailable("INTERNAL_TOKEN is required for secret-broker calls")
    return tok


def _broker_headers(*, include_write_token: bool = False) -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "X-Internal-Token": _internal_token(),
    }
    request_id = (get_request_id_context() or "").strip()
    if request_id:
        headers["X-Request-ID"] = request_id
    if include_write_token:
        tok = _secret_write_token()
        if tok:
            headers["X-Secret-Write-Token"] = tok
    return headers


def _broker_store_secret(name: str, value: str) -> str:
    url = f"{_secret_broker_url()}/secrets/store"
    payload = {"name": name, "value": value}
    timeout = _secret_broker_timeout()

    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.post(url, json=payload, headers=_broker_headers(include_write_token=True))
    except httpx.HTTPError as exc:
        log_event(
            logger,
            40,
            "AUTH_SECRET_BROKER_STORE_FAILED",
            provider="secret-broker",
            target=url,
            outcome="http_error",
            message=str(exc),
        )
        raise SecretStoreUnavailable(f"Secret broker store call failed: {exc}") from exc

    if res.status_code not in (200, 201):
        code = "SECRET_PROVIDER_FAILURE"
        msg = f"Secret broker store failed ({res.status_code})"
        try:
            data = res.json() if res.content else {}
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                code = str(error.get("code") or code)
                msg = str(error.get("message") or msg)
        except ValueError:
            pass
        raise SecretStoreUnavailable(f"{code}: {msg}")

    try:
        data = res.json() if res.content else {}
    except ValueError as exc:
        raise SecretStoreUnavailable("Secret broker store returned invalid JSON") from exc

    envelope_data = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else {}
    ref = str((data or {}).get("ref") or envelope_data.get("ref") or "").strip()
    if not ref:
        raise SecretStoreUnavailable("Secret broker store returned empty ref")
    return ref


def _broker_exists_secret(ref: str) -> bool:
    url = f"{_secret_broker_url()}/secrets/exists"
    timeout = _secret_broker_timeout()
    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.get(url, params={"ref": ref}, headers=_broker_headers())
    except httpx.HTTPError as exc:
        log_event(
            logger,
            40,
            "AUTH_SECRET_BROKER_EXISTS_FAILED",
            provider="secret-broker",
            target=url,
            outcome="http_error",
            message=str(exc),
        )
        raise SecretStoreUnavailable(f"Secret broker exists call failed: {exc}") from exc

    if res.status_code != 200:
        code = "SECRET_PROVIDER_FAILURE"
        msg = f"Secret broker exists failed ({res.status_code})"
        try:
            data = res.json() if res.content else {}
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                code = str(error.get("code") or code)
                msg = str(error.get("message") or msg)
        except ValueError:
            pass
        raise SecretStoreUnavailable(f"{code}: {msg}")

    try:
        data = res.json() if res.content else {}
    except ValueError as exc:
        raise SecretStoreUnavailable("Secret broker exists returned invalid JSON") from exc

    envelope_data = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else {}
    return bool((data or {}).get("exists") or envelope_data.get("exists"))


def _broker_resolve_secret(ref: str) -> str:
    url = f"{_secret_broker_url()}/resolve"
    payload = {"ref": ref}
    timeout = _secret_broker_timeout()

    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.post(url, json=payload, headers=_broker_headers())
    except httpx.HTTPError as exc:
        log_event(
            logger,
            40,
            "AUTH_SECRET_BROKER_RESOLVE_FAILED",
            provider="secret-broker",
            target=url,
            outcome="http_error",
            message=str(exc),
        )
        raise RuntimeError(f"Secret broker resolve call failed: {exc}") from exc

    if res.status_code != 200:
        code = "SECRET_PROVIDER_FAILURE"
        msg = f"Secret broker resolve failed ({res.status_code})"
        try:
            data = res.json() if res.content else {}
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                code = str(error.get("code") or code)
                msg = str(error.get("message") or msg)
        except ValueError:
            pass
        raise RuntimeError(f"{code}: {msg}")

    try:
        data = res.json() if res.content else {}
    except ValueError as exc:
        raise RuntimeError("Secret broker resolve returned invalid JSON") from exc
    envelope_data = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else {}
    value = str((data or {}).get("value") or envelope_data.get("value") or "")
    if not value:
        raise RuntimeError("Secret broker resolve returned empty value")
    return value


# ==================================================
# 🔍 Secret resolution
# ==================================================

def resolve_secret(ref: str, *, default: Optional[str] = None) -> str:
    """
    Resolve a secret reference.

    Supported refs:
      - env://VAR_NAME
      - file:///path/to/file
      - broker-managed refs (optional)

    Behavior:
      - empty ref → default or ""
      - local refs → resolved locally
      - broker refs → resolved via broker if configured
    """
    if not ref:
        return default or ""

    ref = str(ref).strip()

    # -------------------------
    # Local resolution (V1)
    # -------------------------
    if ref.startswith("env://"):
        key = ref[len("env://") :]
        return os.getenv(key, default or "")

    if ref.startswith("file://"):
        path = ref[len("file://") :]
        try:
            return _read_file(path)
        except OSError:
            return default or ""

    if ref.startswith("sm://"):
        try:
            return _broker_resolve_secret(ref)
        except RuntimeError:
            if default is not None:
                return default
            raise

    if default is not None:
        return default
    raise RuntimeError("Unsupported secret ref")


# ==================================================
# 🗄️ Secret storage (AUTH-SERVICE ONLY)
# ==================================================

class SecretStoreUnavailable(RuntimeError):
    pass


def store_secret(name: str, value: str) -> str:
    """
    Store a secret value and return its reference.

    V1 rules:
      - Only auth-service may call this
      - Secret value is NEVER returned
      - Returned ref is persisted in DAL
      - Broker decides storage backend & ref format

    Example returned ref:
      - sm://identity-sources/ad01/bind-password
      - sm://storage-endpoint/smb/fs01/bind-password
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Secret name is required")
    if not value:
        raise ValueError("Secret value is required")

    # Canonical path: delegate storage to secret-broker so all services
    # resolve refs from the same backend.
    try:
        ref = _broker_store_secret(name, value)
        if not _broker_exists_secret(ref):
            raise SecretStoreUnavailable(f"SECRET_STORE_REJECTED: Secret was not confirmed as persisted ({ref})")
        return ref
    except SecretStoreUnavailable as exc:
        raise SecretStoreUnavailable(f"Secret broker store failed: {exc}") from exc
