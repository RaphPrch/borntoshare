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
    """Raised when no identity source is configured (404 from core-service)."""


def _internal_headers() -> Dict[str, str]:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
    }
    return {**headers, **build_internal_headers()}


async def core_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = settings.CORE_URL.rstrip("/") + path
    timeout = getattr(settings, "CORE_TIMEOUT_SECONDS", 5)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(url, json=payload, headers=_internal_headers())
    except httpx.TimeoutException as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="core",
            target=url,
            outcome="timeout",
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        raise AuthUnavailable("core-service timeout") from exc
    except httpx.RequestError as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="core",
            target=url,
            outcome="network_error",
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        raise AuthUnavailable("core-service unavailable") from exc

    if res.status_code == 404:
        raise IdentitySourceNotFound()

    if res.status_code >= 500:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="core",
            target=url,
            outcome="server_error",
            status_code=res.status_code,
            error_code="INTERNAL_ERROR",
        )
        raise AuthUnavailable("core-service unavailable")

    if res.status_code != 200:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_CORE_BAD_RESPONSE",
            provider="core",
            target=url,
            outcome="bad_response",
            status_code=res.status_code,
            error_code="BAD_REQUEST",
        )
        raise AuthUnavailable("core-service bad response")

    try:
        payload_data = res.json() if res.content else {}
    except ValueError as exc:
        raise AuthUnavailable("core-service bad JSON response") from exc

    if not isinstance(payload_data, dict):
        raise AuthUnavailable("core-service bad response payload")
    return payload_data


async def core_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    url = settings.CORE_URL.rstrip("/") + path
    timeout = getattr(settings, "CORE_TIMEOUT_SECONDS", 5)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.get(url, headers=_internal_headers(), params=params)
    except httpx.TimeoutException as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="core",
            target=url,
            outcome="timeout",
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        raise AuthUnavailable("core-service timeout") from exc
    except httpx.RequestError as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="core",
            target=url,
            outcome="network_error",
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        raise AuthUnavailable("core-service unavailable") from exc

    if res.status_code == 404:
        raise IdentitySourceNotFound()

    if res.status_code >= 500:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="core",
            target=url,
            outcome="server_error",
            status_code=res.status_code,
            error_code="INTERNAL_ERROR",
        )
        raise AuthUnavailable("core-service unavailable")

    if res.status_code != 200:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_CORE_BAD_RESPONSE",
            provider="core",
            target=url,
            outcome="bad_response",
            status_code=res.status_code,
            error_code="BAD_REQUEST",
        )
        raise AuthUnavailable("core-service bad response")

    try:
        payload_data = res.json() if res.content else {}
    except ValueError as exc:
        raise AuthUnavailable("core-service bad JSON response") from exc

    if not isinstance(payload_data, dict):
        raise AuthUnavailable("core-service bad response payload")
    return payload_data


async def core_get_active_identity_source(
    source_type: str = "ad",
) -> Dict[str, Any]:
    return await core_get(
        "/api/internal/identity-sources/active",
        params={"type": source_type},
    )


async def core_get_active_identity_source_by_domain(
    source_type: str,
    domain: str,
) -> Dict[str, Any]:
    return await core_get(
        "/api/internal/identity-sources/resolve",
        params={"type": source_type, "domain": domain},
    )


async def core_get_identity_roles(identity_id: str) -> Dict[str, Any]:
    return await core_get(f"/api/internal/identities/{identity_id}/roles")


async def core_get_identity_source_by_id(source_id: int) -> Dict[str, Any]:
    return await core_get(f"/api/internal/identity-sources/{int(source_id)}")


async def core_resolve_login_identity(
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
    return await core_post("/api/internal/identities/resolve-login", payload)


async def core_resolve_ad_identity(
    *,
    external_id: str | None = None,
    username: str | None = None,
    email: str | None = None,
    identity_source_id: int | None = None,
    provision_if_entitled: bool = False,
) -> Dict[str, Any]:
    payload = {
        "external_id": external_id,
        "username": username,
        "email": email,
        "identity_source_id": identity_source_id,
        "provision_if_entitled": provision_if_entitled,
    }
    return await core_post("/api/internal/identities/resolve-ad", payload)


async def core_resolve_directory_login(
    *,
    username: str | None = None,
    upn_hint: str | None = None,
    domain_hint: str | None = None,
) -> Dict[str, Any]:
    """AD source whose last snapshot knows a user who was not imported (login through an entitled group)."""
    payload = {"username": username, "upn_hint": upn_hint, "domain_hint": domain_hint}
    return await core_post("/api/internal/identities/resolve-directory-login", payload)


async def core_list_sso_providers() -> Dict[str, Any]:
    return await core_get("/api/internal/sso-providers")


async def core_get_sso_provider(provider_id: int) -> Dict[str, Any]:
    return await core_get(f"/api/internal/sso-providers/{int(provider_id)}")


async def core_resolve_sso_identity(provider_id: int, claims: Dict[str, Any]) -> Dict[str, Any]:
    return await core_post(f"/api/internal/sso-providers/{int(provider_id)}/resolve-identity", claims)
