from __future__ import annotations

import hmac
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core import store
from core.crypto import encrypt, get_master_key, get_master_key_id
from core.api_envelope import error_payload as api_error_payload, ok_data
from core.errors import (
    SecretBrokerError,
    SecretInvalidRefError,
    SecretNotFoundError,
    SecretPersistenceFailureError,
    SecretProviderFailureError,
    SecretStoreRejectedError,
)
from core.internal_auth import require_internal_token
from core.settings import settings
from providers.path_utils import build_sm_ref
from providers.registry import resolve_secret
from schemas import (
    ErrorResponse,
    ResolveRequest,
    ResolveResponse,
    StoreResponse,
    RotateResponse,
    RevokeResponse,
    ExistsResponse,
)

router = APIRouter(tags=["secrets"])
logger = logging.getLogger("secret-broker.secrets")

# ==================================================
# 🧠 In-memory cache (read acceleration, not persistence)
# ==================================================

_inmemory_secrets: dict[str, tuple[str, float]] = {}


def _store_secret_cache(ref: str, value: str) -> None:
    ttl = int(getattr(settings, "secret_mem_ttl_sec", 60) or 60)
    _inmemory_secrets[ref] = (value, time.time() + ttl)


def _get_secret_cache(ref: str) -> Optional[str]:
    item = _inmemory_secrets.get(ref)
    if not item:
        return None
    value, expires_at = item
    if time.time() > expires_at:
        _inmemory_secrets.pop(ref, None)
        return None
    return value


def _revoke_secret_cache(ref: str) -> None:
    _inmemory_secrets.pop(ref, None)


# ==================================================
# 📥 Schemas
# ==================================================


class StoreRequest(BaseModel):
    name: str
    value: str


class RotateRequest(BaseModel):
    ref: str
    new_value: str


class RevokeRequest(BaseModel):
    ref: str


# ==================================================
# 🔐 Helpers
# ==================================================


def _error_payload(exc: SecretBrokerError, *, ref: Optional[str] = None) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    if ref or exc.ref:
        details["ref"] = ref or exc.ref
    if exc.provider:
        details["provider"] = exc.provider
    return api_error_payload(
        code=exc.code,
        message=exc.message,
        details=details,
    )


def _raise_http(exc: SecretBrokerError, *, ref: Optional[str] = None) -> None:
    payload = _error_payload(exc, ref=ref)
    logger.warning(
        "secret.error",
        extra={
            "error_code": exc.code,
            "http_status": exc.http_status,
            "secret_ref": payload["error"].get("ref"),
            "provider": exc.provider,
        },
    )
    raise HTTPException(status_code=exc.http_status, detail=payload)


def _is_allowed(ref: str) -> bool:
    allowed = [p.strip() for p in (settings.allowed_prefixes or "").split(",") if p.strip()]
    if not allowed:
        return True
    return any(ref.startswith(p) for p in allowed)


def _pick_ref(req: ResolveRequest) -> str:
    return (req.ref or "").strip()


def _make_ref(name: str) -> str:
    return _make_sm_ref(name)


def _make_sm_ref(name: str) -> str:
    return build_sm_ref(name)


def _require_write_token(request: Request) -> None:
    if not settings.write_token:
        return
    provided = str(request.headers.get("X-Secret-Write-Token") or "")
    expected = str(settings.write_token or "")
    if not provided or not hmac.compare_digest(provided, expected):
        _raise_http(SecretStoreRejectedError(message="Write token required"))


def _persist_secret_or_raise(name: str, ref: str, value: str, *, must_exist: bool = False) -> str:
    try:
        ref = build_sm_ref(ref)
        if must_exist and store.get(ref) is None:
            raise SecretNotFoundError(ref=ref, provider="database")
        iv, ciphertext = encrypt(ref, value)
        store.put(ref, name, iv, ciphertext, get_master_key_id())
        return ref
    except SecretBrokerError:
        raise
    except Exception as exc:
        logger.exception(
            "secret.persistence.failed",
            extra={"error_code": "SECRET_PERSISTENCE_FAILURE", "secret_ref": ref, "provider": "database"},
        )
        raise SecretPersistenceFailureError(
            message="Secret broker persistence failed",
            ref=ref,
            provider="database",
        ) from exc


def _ensure_startup_prereqs() -> None:
    # The database may not exist yet (first installation): only the key is required to start
    try:
        _ = get_master_key()
    except Exception as exc:
        logger.exception("secret-broker.boot.master_key.invalid", extra={"error_code": "SECRET_PROVIDER_FAILURE"})
        raise RuntimeError("SECRET_PROVIDER_FAILURE: invalid or missing B2S_SECRET_MASTER_KEY") from exc

    logger.info("secret-broker.boot.master_key.loaded", extra={"event": "secret.master_key.loaded"})


def ensure_boot_checks() -> None:
    _ensure_startup_prereqs()


# ==================================================
# 🔍 Resolve secret
# ==================================================


@router.post(
    "/resolve",
    response_model=ResolveResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    dependencies=[Depends(require_internal_token)],
)
def resolve(req: ResolveRequest) -> ResolveResponse:
    ref = _pick_ref(req)
    if not ref:
        _raise_http(SecretInvalidRefError(message="Missing ref", ref=ref), ref=ref)

    if not _is_allowed(ref):
        _raise_http(SecretInvalidRefError(message="Secret prefix not allowed", ref=ref), ref=ref)

    if ref.startswith("mem://"):
        _raise_http(SecretInvalidRefError(message="mem:// is not supported", ref=ref), ref=ref)

    value = _get_secret_cache(ref)
    if value is not None:
        return ResolveResponse(**ok_data({"value": value}))

    try:
        value = resolve_secret(ref)
    except SecretBrokerError as exc:
        _raise_http(exc, ref=ref)
    except Exception as exc:
        _raise_http(
            SecretProviderFailureError(
                message="Unexpected secret provider failure",
                ref=ref,
            ),
            ref=ref,
        )

    _store_secret_cache(ref, value)
    return ResolveResponse(**ok_data({"value": value}))


# ==================================================
# 🗄️ Store secret (AUTH-SERVICE ONLY)
# ==================================================


@router.post(
    "/secrets/store",
    response_model=StoreResponse,
    responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    dependencies=[Depends(require_internal_token)],
)
def store_secret(payload: StoreRequest, request: Request) -> StoreResponse:
    _ensure_startup_prereqs()

    if not settings.allow_write:
        _raise_http(SecretStoreRejectedError(message="Secret write disabled"))

    _require_write_token(request)

    name = payload.name.strip()
    if not name:
        _raise_http(SecretInvalidRefError(message="Missing secret name"))

    try:
        ref = _make_ref(name)
    except SecretBrokerError as exc:
        _raise_http(exc)

    if not _is_allowed(ref):
        _raise_http(SecretInvalidRefError(message="Secret prefix not allowed", ref=ref), ref=ref)

    try:
        persisted_ref = _persist_secret_or_raise(name, ref, payload.value)
    except SecretBrokerError as exc:
        _raise_http(exc, ref=ref)

    _store_secret_cache(persisted_ref, payload.value)

    return StoreResponse(**ok_data({"ref": persisted_ref}))


@router.post(
    "/secrets/rotate",
    response_model=RotateResponse,
    responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    dependencies=[Depends(require_internal_token)],
)
def rotate_secret(payload: RotateRequest, request: Request) -> RotateResponse:
    _ensure_startup_prereqs()

    if not settings.allow_write:
        _raise_http(SecretStoreRejectedError(message="Secret write disabled"))

    _require_write_token(request)

    ref = (payload.ref or "").strip()
    if not ref or not ref.startswith("sm://"):
        _raise_http(SecretInvalidRefError(message="Rotation requires an sm:// ref", ref=ref), ref=ref)

    if not _is_allowed(ref):
        _raise_http(SecretInvalidRefError(message="Secret prefix not allowed", ref=ref), ref=ref)

    try:
        _persist_secret_or_raise(name=ref, ref=ref, value=payload.new_value, must_exist=True)
    except SecretBrokerError as exc:
        _raise_http(exc, ref=ref)

    _store_secret_cache(ref, payload.new_value)
    return RotateResponse(**ok_data({"ref": ref}))


@router.post(
    "/secrets/revoke",
    response_model=RevokeResponse,
    responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    dependencies=[Depends(require_internal_token)],
)
def revoke_secret(payload: RevokeRequest, request: Request) -> RevokeResponse:
    _ensure_startup_prereqs()

    if not settings.allow_write:
        _raise_http(SecretStoreRejectedError(message="Secret write disabled"))

    _require_write_token(request)

    ref = str(payload.ref or "").strip()
    if not ref or not ref.startswith("sm://"):
        _raise_http(SecretInvalidRefError(message="Revoke requires an sm:// ref", ref=ref), ref=ref)

    if not _is_allowed(ref):
        _raise_http(SecretInvalidRefError(message="Secret prefix not allowed", ref=ref), ref=ref)

    try:
        ref = build_sm_ref(ref)
        store.delete(ref)
    except SecretBrokerError as exc:
        _raise_http(exc, ref=ref)

    _revoke_secret_cache(ref)
    return RevokeResponse(**ok_data({"ref": ref, "revoked": True}))


@router.get("/secrets/exists", response_model=ExistsResponse, dependencies=[Depends(require_internal_token)])
def secret_exists(ref: str) -> ExistsResponse:
    checked_ref = str(ref or "").strip()
    if not checked_ref:
        _raise_http(SecretInvalidRefError(message="Missing ref", ref=checked_ref), ref=checked_ref)
    if not checked_ref.startswith("sm://"):
        return ExistsResponse(**ok_data({"ref": checked_ref, "exists": False}))

    try:
        checked_ref = build_sm_ref(checked_ref)
        exists = store.get(checked_ref) is not None
    except SecretBrokerError as exc:
        _raise_http(exc, ref=checked_ref)

    return ExistsResponse(**ok_data({"ref": checked_ref, "exists": exists}))
