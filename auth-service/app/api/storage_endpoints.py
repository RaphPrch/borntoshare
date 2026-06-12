from __future__ import annotations

import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.internal_auth import require_internal_token
from app.core.logging import get_logger, log_event
from app.services.secret_broker_client import SecretStoreUnavailable, store_secret

logger = get_logger(__name__)

router = APIRouter(prefix="/internal/storage-endpoints", tags=["internal_storage_endpoints"])


class StorageEndpointSecretPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    protocol: str | None = None
    host: str | None = None
    bind_dn: str | None = None
    bind_password_ref: str | None = None
    bind_password: str | None = Field(default=None, repr=False)


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
    return value or "storage-endpoint"


def _store_endpoint_bind_password(payload: StorageEndpointSecretPayload | dict[str, Any]) -> str | None:
    data = payload if isinstance(payload, StorageEndpointSecretPayload) else StorageEndpointSecretPayload.model_validate(payload)
    bind_password = (data.bind_password or "").strip()
    provided_ref = (data.bind_password_ref or "").strip()

    if not bind_password:
        return provided_ref or None

    if not (data.bind_dn or "").strip():
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="bind_dn required to store endpoint credentials",
        )

    protocol = _slugify(data.protocol or "smb")
    name = provided_ref or f"storage-endpoint/{protocol}/{_slugify(data.name or data.host or 'endpoint')}/bind-password"

    try:
        return store_secret(name, bind_password)
    except SecretStoreUnavailable as exc:
        logger.warning("Storage endpoint secret store failed | ref=%s | err=%s", name, exc)
        raise _http_error(
            status.HTTP_502_BAD_GATEWAY,
            code="AUTH_UNAVAILABLE",
            message="Secret broker store failed",
        ) from exc


@router.post("/secret-ref", summary="Store storage endpoint bind password and return ref (internal)")
async def store_bind_password_ref(
    payload: StorageEndpointSecretPayload | dict[str, Any],
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
):
    require_internal_token(x_internal_token, source="storage_endpoints.secret_ref")
    ref = _store_endpoint_bind_password(payload)
    if not ref:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="bind_password required",
        )
    log_event(
        logger,
        logging.INFO,
        "AUTH_STORAGE_ENDPOINT_SECRET_REF",
        outcome="stored",
    )
    return {"bind_password_ref": ref}
