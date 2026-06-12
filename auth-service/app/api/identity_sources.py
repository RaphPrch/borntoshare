from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, status

from app.core.config import get_settings
from app.core.internal_auth import require_internal_token
from app.core.internal_token import build_internal_headers
from app.core.logging import get_logger, log_event
from app.schemas.identity_sources import ADIdentitySourceTestPayload, ADSecretUpsertPayload
from app.services.secret_broker_client import store_secret, SecretStoreUnavailable

settings = get_settings()
logger = get_logger(__name__)

router = APIRouter(prefix="/internal/identity-sources", tags=["internal_identity_sources"])


def _http_error(
    status_code: int,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": str(code),
            "message": str(message),
            "details": dict(details or {}),
        },
    )


def _slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "identity-source"


async def _dal_request(method: str, path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    url = settings.DAL_URL.rstrip("/") + path
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        **build_internal_headers(),
    }
    timeout = getattr(settings, "DAL_TIMEOUT_SECONDS", 5)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.request(method, url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_UNAVAILABLE",
            message="DAL timeout",
        ) from exc
    except httpx.RequestError as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_UNAVAILABLE",
            message="DAL unavailable",
        ) from exc

    if res.status_code in (200, 201):
        return res.json() if res.content else {}

    if res.status_code >= 500:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_UNAVAILABLE",
            message="DAL unavailable",
            details={"status_code": int(res.status_code)},
        )

    try:
        detail = res.json()
    except ValueError:
        detail = {}

    if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
        nested = dict(detail.get("error") or {})
        return_code = str(nested.get("code") or "BAD_REQUEST").strip() or "BAD_REQUEST"
        return_message = str(nested.get("message") or "DAL request failed").strip() or "DAL request failed"
        return_details = nested.get("details") if isinstance(nested.get("details"), dict) else {}
        raise _http_error(
            int(res.status_code),
            code=return_code,
            message=return_message,
            details=return_details,
        )

    raise _http_error(
        int(res.status_code),
        code="BAD_REQUEST",
        message="DAL request failed",
        details={"status_code": int(res.status_code)},
    )


def _to_upsert_payload(payload: ADSecretUpsertPayload | dict[str, Any]) -> ADSecretUpsertPayload:
    if isinstance(payload, ADSecretUpsertPayload):
        return payload
    return ADSecretUpsertPayload.model_validate(payload)


def _to_test_payload(payload: ADIdentitySourceTestPayload | dict[str, Any]) -> ADIdentitySourceTestPayload:
    if isinstance(payload, ADIdentitySourceTestPayload):
        return payload
    return ADIdentitySourceTestPayload.model_validate(payload)


def _store_ad_bind_password(payload: ADSecretUpsertPayload | dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    data = _to_upsert_payload(payload).model_dump(exclude_none=True)

    if (data.get("type") or "").lower() != "ad":
        return data, None

    bind_password = data.pop("bind_password", None)
    if not bind_password:
        provided_ref = (data.get("bind_password_ref") or "").strip()
        return data, provided_ref or None

    # If caller provided a ref, use it, else generate a stable ref.
    provided_ref = (data.get("bind_password_ref") or "").strip()

    if provided_ref:
        ref = provided_ref
    else:
        # Prefer explicit env var if you want deterministic naming across environments.
        default_ref = (settings.DEFAULT_AD_BIND_PASSWORD_REF or "").strip()
        if default_ref:
            ref = default_ref
        else:
            # Broker-backed reference (not stored in DAL).
            # Use name/host to generate a stable-ish key.
            name = data.get("name") or data.get("host") or "ad"
            ref = f"identity-sources/{_slugify(str(name))}/bind-password"

    try:
        ref = store_secret(ref, str(bind_password))
    except SecretStoreUnavailable as exc:
        logger.warning("Secret store failed | ref=%s | err=%s", ref, exc)
        raise _http_error(
            status.HTTP_502_BAD_GATEWAY,
            code="AUTH_UNAVAILABLE",
            message="Secret broker store failed",
        ) from exc

    # Persist ref only
    data["bind_password_ref"] = ref
    return data, ref


def _sanitize_ad_test_payload(payload: ADIdentitySourceTestPayload | dict[str, Any]) -> dict[str, Any]:
    data = _to_test_payload(payload).model_dump(exclude_none=True)
    data.pop("bind_password", None)
    return data


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create identity source (internal)")
async def create_identity_source(
    payload: ADSecretUpsertPayload | dict[str, Any],
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
):
    require_internal_token(x_internal_token, source="identity_sources.create")
    data, _ = _store_ad_bind_password(payload)
    log_event(
        logger,
        logging.INFO,
        "AUTH_IDENTITY_SOURCE_CREATE",
        outcome="request",
    )
    return await _dal_request("POST", "/api/identity-sources", payload=data)


@router.patch("/{source_id}", summary="Update identity source (internal)")
async def update_identity_source(
    source_id: int,
    payload: ADSecretUpsertPayload | dict[str, Any],
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
):
    require_internal_token(x_internal_token, source="identity_sources.update")
    data = _to_upsert_payload(payload).model_dump(exclude_none=True)
    data["id"] = source_id
    data, _ = _store_ad_bind_password(data)
    log_event(
        logger,
        logging.INFO,
        "AUTH_IDENTITY_SOURCE_UPDATE",
        target=source_id,
        outcome="request",
    )
    return await _dal_request("PATCH", f"/api/identity-sources/{source_id}", payload=data)


@router.post("/secret-ref", summary="Store bind password and return ref (internal)")
async def store_bind_password_ref(
    payload: ADSecretUpsertPayload | dict[str, Any],
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
):
    require_internal_token(x_internal_token, source="identity_sources.secret_ref")
    data = _to_upsert_payload(payload).model_dump(exclude_none=True)
    if not data.get("type"):
        data["type"] = "ad"
    data, ref = _store_ad_bind_password(data)
    if not ref:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="bind_password required",
        )
    return {"bind_password_ref": ref}


@router.post("/test", summary="Test identity source configuration (internal)")
async def test_identity_source_internal(
    payload: ADIdentitySourceTestPayload | dict[str, Any],
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
):
    require_internal_token(x_internal_token, source="identity_sources.test")
    data = _sanitize_ad_test_payload(payload)
    source_type = (data.get("type") or "").lower()
    if source_type and source_type != "ad":
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="Only AD is supported",
        )

    host = (data.get("host") or "").strip()
    base_dn = (data.get("base_dn") or "").strip()
    bind_dn = (data.get("bind_dn") or "").strip()
    if not host or not base_dn or not bind_dn:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="Missing required AD fields",
            details={"required": ["host", "base_dn", "bind_dn"]},
        )

    log_event(
        logger,
        logging.INFO,
        "AUTH_IDENTITY_SOURCE_TEST",
        target=host,
        outcome="request",
    )
    return await _dal_request("POST", "/api/identity-sources/test", payload=data)
