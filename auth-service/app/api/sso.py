"""SSO sign-in (Keycloak / OpenID Connect): login buttons, start, callback, provider test."""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.auth import _emit_activity_event, _http_error, _require_platform_admin, _request_id, open_session
from app.core.deps import get_current_user
from app.core.logging import get_logger, log_event
from app.schemas.auth import LoginResponse, UserInfo
from app.services import oidc
from app.services.internal_clients import (
    IdentitySourceNotFound,
    core_get_sso_provider,
    core_list_sso_providers,
    core_resolve_sso_identity,
)
from app.services.providers.base import AuthUnavailable
from app.services.secret_broker_client import resolve_secret

router = APIRouter(prefix="/auth/sso", tags=["sso"])
logger = get_logger(__name__)

REFUSALS = {
    "NOT_ENTITLED": "This account is not authorized in BornToShare",
    "PROVIDER_DISABLED": "This sign-in method is disabled",
    "MISSING_CLAIMS": "The identity provider did not send the user name",
}


def _safe_return_to(value: str | None) -> str:
    """Only a path of this site (no open redirect)."""
    target = str(value or "").strip()
    parts = urlsplit(target)
    if not target.startswith("/") or target.startswith("//") or parts.scheme or parts.netloc:
        return "/dashboard"
    return target


async def _provider(provider_id: int) -> dict[str, Any]:
    try:
        return await core_get_sso_provider(provider_id)
    except IdentitySourceNotFound as exc:
        raise _http_error(status.HTTP_404_NOT_FOUND, code="SSO_PROVIDER_NOT_FOUND", message="This sign-in method is not available") from exc


def _secret(provider: dict[str, Any]) -> str | None:
    ref = provider.get("client_secret_ref")
    if not ref:
        return None  # public client: PKCE only
    return resolve_secret(ref, default="") or None


@router.get("/providers")
async def list_providers() -> dict[str, Any]:
    """Login page buttons (no secret, no URL)."""
    try:
        data = await core_list_sso_providers()
    except (IdentitySourceNotFound, AuthUnavailable):
        return {"providers": []}
    return {"providers": data.get("providers") or []}


class StartRequest(BaseModel):
    provider_id: int
    redirect_uri: str = Field(min_length=8, max_length=512)
    return_to: Optional[str] = Field(default=None, max_length=512)


@router.post("/start")
async def start(payload: StartRequest) -> dict[str, str]:
    provider = await _provider(payload.provider_id)
    try:
        url = await oidc.authorization_url(provider, redirect_uri=payload.redirect_uri, return_to=_safe_return_to(payload.return_to))
    except oidc.OidcError as exc:
        raise _http_error(status.HTTP_503_SERVICE_UNAVAILABLE, code=exc.code, message=exc.message) from exc
    return {"authorization_url": url}


class CallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=10, max_length=256)


@router.post("/callback", response_model=None)
async def callback(payload: CallbackRequest, request: Request, response: Response) -> dict[str, Any]:
    rid = _request_id(request)
    pending = oidc.state_store.pop(payload.state)
    if pending is None:
        raise _http_error(status.HTTP_400_BAD_REQUEST, code="SSO_STATE_INVALID", message="This sign-in link expired or was already used: sign in again")
    provider = await _provider(pending.provider_id)
    try:
        claims = await oidc.exchange_code(provider, _secret(provider), pending, code=payload.code)
    except oidc.OidcError as exc:
        log_event(logger, logging.WARNING, "AUTH_SSO_FAILED", request_id=rid, provider="oidc", outcome=exc.code.lower(), error_code=exc.code, message=exc.message)
        raise _http_error(status.HTTP_401_UNAUTHORIZED, code=exc.code, message=exc.message) from exc

    username = str(claims.get(provider.get("username_claim") or "preferred_username") or claims.get("preferred_username") or "").strip()
    decision = await core_resolve_sso_identity(
        int(provider["id"]),
        {
            "sub": str(claims.get("sub") or ""),
            "username": username or str(claims.get("sub") or ""),
            "email": claims.get("email"),
            "name": claims.get("name"),
            "roles": oidc.claim_values(claims, provider.get("roles_claim") or "realm_access.roles"),
        },
    )
    if not decision.get("found") or decision.get("is_active") is False:
        reason = str(decision.get("reason_code") or "INACTIVE")
        await _emit_activity_event(
            action="auth.login",
            outcome="failure",
            severity="warning",
            actor_type="user",
            actor_id=None,
            actor_display=username[:190] or None,
            target_type="identity",
            target_id=None,
            target_display=username[:190] or None,
            metadata_json={"reason": reason, "provider": "sso", "sso_provider": provider.get("name")},
            correlation_id=rid,
        )
        raise _http_error(status.HTTP_403_FORBIDDEN, code="ACCOUNT_NOT_AUTHORIZED", message=REFUSALS.get(reason, "This account is not authorized in BornToShare"))

    user = UserInfo(
        identity_id=str(decision["identity_id"]),
        identity_source_id=int(provider.get("identity_source_id") or 0) or None,
        username=username,
        display_name=claims.get("name") or username,
        email=claims.get("email"),
        external_id=str(claims.get("sub") or ""),
        auth_source="oidc",
    )
    session: LoginResponse = await open_session(request, response, user, "sso")
    return {"user": session.user.model_dump(), "return_to": pending.return_to}


class TestRequest(BaseModel):
    provider_id: Optional[int] = None
    base_url: Optional[str] = None
    realm: Optional[str] = None
    client_id: Optional[str] = None
    client_secret_ref: Optional[str] = None
    verify_tls: bool = True


@router.post("/test")
async def test(payload: TestRequest, user: UserInfo = Depends(get_current_user)) -> dict[str, Any]:
    """Administrators: test a provider, saved (provider_id) or being entered (fields)."""
    _require_platform_admin(user)
    provider: dict[str, Any] = {}
    if payload.provider_id:
        try:
            provider = await core_get_sso_provider(payload.provider_id)
        except IdentitySourceNotFound:
            provider = {}
    for key in ("base_url", "realm", "client_id", "client_secret_ref"):
        value = getattr(payload, key)
        if value:
            provider[key] = value
    provider["verify_tls"] = payload.verify_tls
    if not provider.get("base_url") or not provider.get("realm") or not provider.get("client_id"):
        raise HTTPException(status_code=422, detail={"code": "BAD_REQUEST", "message": "Server URL, realm and client ID are required"})
    try:
        result = await oidc.test_provider(provider, _secret(provider))
    except oidc.OidcError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}
    return {"ok": True, "message": "Keycloak answered, client accepted", **result}
