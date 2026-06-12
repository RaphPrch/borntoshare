from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from app.core.internal_token import build_internal_headers
from app.core.config import get_settings
from app.core.logging import get_logger, log_event
from app.services.providers.base import AuthUnavailable

settings = get_settings()
logger = get_logger(__name__)


class IdentitySourceNotFound(Exception):
    """Raised when no identity source is configured (404 from DAL)."""


def _internal_headers() -> Dict[str, str]:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
    }
    return {**headers, **build_internal_headers()}


async def dal_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = settings.DAL_URL.rstrip("/") + path
    timeout = getattr(settings, "DAL_TIMEOUT_SECONDS", 5)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(url, json=payload, headers=_internal_headers())
    except httpx.TimeoutException as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="dal",
            target=url,
            outcome="timeout",
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        raise AuthUnavailable("DAL timeout") from exc
    except httpx.RequestError as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="dal",
            target=url,
            outcome="network_error",
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        raise AuthUnavailable("DAL unavailable") from exc

    if res.status_code == 404:
        raise IdentitySourceNotFound()

    if res.status_code >= 500:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="dal",
            target=url,
            outcome="server_error",
            status_code=res.status_code,
            error_code="INTERNAL_ERROR",
        )
        raise AuthUnavailable("DAL unavailable")

    if res.status_code != 200:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_DAL_BAD_RESPONSE",
            provider="dal",
            target=url,
            outcome="bad_response",
            status_code=res.status_code,
            error_code="BAD_REQUEST",
        )
        raise AuthUnavailable("DAL bad response")

    try:
        payload_data = res.json() if res.content else {}
    except ValueError as exc:
        raise AuthUnavailable("DAL bad JSON response") from exc

    if not isinstance(payload_data, dict):
        raise AuthUnavailable("DAL bad response payload")
    return payload_data


async def dal_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    url = settings.DAL_URL.rstrip("/") + path
    timeout = getattr(settings, "DAL_TIMEOUT_SECONDS", 5)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.get(url, headers=_internal_headers(), params=params)
    except httpx.TimeoutException as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="dal",
            target=url,
            outcome="timeout",
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        raise AuthUnavailable("DAL timeout") from exc
    except httpx.RequestError as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="dal",
            target=url,
            outcome="network_error",
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        raise AuthUnavailable("DAL unavailable") from exc

    if res.status_code == 404:
        raise IdentitySourceNotFound()

    if res.status_code >= 500:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="dal",
            target=url,
            outcome="server_error",
            status_code=res.status_code,
            error_code="INTERNAL_ERROR",
        )
        raise AuthUnavailable("DAL unavailable")

    if res.status_code != 200:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_DAL_BAD_RESPONSE",
            provider="dal",
            target=url,
            outcome="bad_response",
            status_code=res.status_code,
            error_code="BAD_REQUEST",
        )
        raise AuthUnavailable("DAL bad response")

    try:
        payload_data = res.json() if res.content else {}
    except ValueError as exc:
        raise AuthUnavailable("DAL bad JSON response") from exc

    if not isinstance(payload_data, dict):
        raise AuthUnavailable("DAL bad response payload")
    return payload_data


async def dal_get_active_identity_source(
    source_type: str = "ad",
) -> Dict[str, Any]:
    return await dal_get(
        "/api/internal/identity-sources/active",
        params={"type": source_type},
    )


async def dal_get_active_identity_source_by_domain(
    source_type: str,
    domain: str,
) -> Dict[str, Any]:
    return await dal_get(
        "/api/internal/identity-sources/resolve",
        params={"type": source_type, "domain": domain},
    )


async def dal_get_identity_roles(identity_id: str) -> Dict[str, Any]:
    return await dal_get(f"/api/internal/identities/{identity_id}/roles")


async def dal_get_identity_source_by_id(source_id: int) -> Dict[str, Any]:
    return await dal_get(f"/api/internal/identity-sources/{int(source_id)}")


async def dal_resolve_login_identity(
    *,
    login: str | None = None,
    username: str | None = None,
    upn_hint: str | None = None,
    domain_hint: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "login": login,
        "username": username,
        "upn_hint": upn_hint,
        "domain_hint": domain_hint,
    }
    return await dal_post("/api/internal/identities/resolve-login", payload)


async def dal_resolve_ad_identity(
    *,
    external_id: str | None = None,
    username: str | None = None,
    email: str | None = None,
    identity_source_id: int | None = None,
) -> Dict[str, Any]:
    payload = {
        "external_id": external_id,
        "username": username,
        "email": email,
        "identity_source_id": identity_source_id,
    }
    return await dal_post("/api/internal/identities/resolve-ad", payload)
