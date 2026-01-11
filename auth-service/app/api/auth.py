# app/api/auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.providers.registry import choose_provider, build_registry, ordered_providers
from app.core.session_store import get_session_store
from app.core.rbac import compute_permissions
from app.core.deps import get_current_user
from app.core.keycloak_state import kc_state_store
from app.core.keycloak_flow import pkce_challenge, authorize_url, handle_callback
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserInfo,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LogoutResponse,
    KeycloakCallbackResponse,
)

settings = get_settings()
store = get_session_store()
logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/providers")
async def providers() -> dict:
    """List enabled authentication providers for UI selection."""
    registry = build_registry()
    ordered = ordered_providers(registry)
    names = [p.name for p in ordered] if ordered else sorted(registry.keys())
    return {
        "default": settings.DEFAULT_AUTH_PROVIDER,
        "enabled": names,
        "available": sorted(registry.keys()),
    }


# ------------------------------------------------------------------
# Cookies helpers
# ------------------------------------------------------------------
def _is_https_request(request: Request) -> bool:
    """
    Detect if the *client-facing* request is HTTPS.
    Works behind reverse proxies via X-Forwarded-Proto.
    """
    xf_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if xf_proto:
        return xf_proto == "https"
    return request.url.scheme == "https"


def _cookie_domain() -> str | None:
    """Allow config to omit domain (recommended in dev)."""
    d = getattr(settings, "COOKIE_DOMAIN", None)
    return d or None


def _cookie_samesite() -> str:
    """Normalize SameSite values for Starlette: 'lax'|'strict'|'none'."""
    v = (getattr(settings, "COOKIE_SAMESITE", "lax") or "lax").lower()
    return v if v in {"lax", "strict", "none"} else "lax"


def _should_set_secure_cookie(request: Request) -> bool:
    """
    Final decision:
    - HTTP  -> secure=False (otherwise browser rejects it)
    - HTTPS -> secure=True
    """
    return _is_https_request(request)


def _set_session_cookie(request: Request, response: Response, session_id: str) -> None:
    """Set session cookie with safe dev/prod behavior."""
    secure = _should_set_secure_cookie(request)
    samesite = _cookie_samesite()
    domain = _cookie_domain()

    # If SameSite=None -> Secure must be True, otherwise modern browsers will reject it.
    if samesite == "none" and not secure:
        logger.warning(
            "[AUTH][COOKIE] SameSite=None requires Secure; downgrading SameSite to 'lax' for HTTP/dev"
        )
        samesite = "lax"

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=secure,
        samesite=samesite,
        domain=domain,
        path="/",
    )

    # IMPORTANT: do NOT use reserved LogRecord keys like "name" in extra={}
    logger.info(
        "[AUTH][COOKIE] set session cookie",
        extra={
            "cookie_name": settings.SESSION_COOKIE_NAME,
            "secure": secure,
            "samesite": samesite,
            "domain": domain,
            "path": "/",
        },
    )


def _clear_session_cookie(request: Request, response: Response) -> None:
    """Clear session cookie (match attributes: domain/path/samesite/secure)."""
    secure = _should_set_secure_cookie(request)
    samesite = _cookie_samesite()
    domain = _cookie_domain()

    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        domain=domain,
        path="/",
        samesite=samesite,
        secure=secure,
    )

    # IMPORTANT: do NOT use reserved LogRecord keys like "name" in extra={}
    logger.info(
        "[AUTH][COOKIE] cleared session cookie",
        extra={
            "cookie_name": settings.SESSION_COOKIE_NAME,
            "secure": secure,
            "samesite": samesite,
            "domain": domain,
            "path": "/",
        },
    )


# ------------------------------------------------------------------
# Auth endpoints
# ------------------------------------------------------------------
@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    rid = getattr(request.state, "request_id", "-")

    provider_name = payload.provider or settings.DEFAULT_AUTH_PROVIDER
    provider = choose_provider(provider_name)

    logger.info(
        "LOGIN attempt | rid=%s | provider=%s | username=%s",
        rid,
        provider.name,
        payload.username,
    )

    try:
        user = await provider.authenticate(payload.username, payload.password)
        user.permissions = compute_permissions(user.roles)
    except Exception as e:
        logger.warning(
            "LOGIN failed | rid=%s | provider=%s | username=%s | err=%s",
            rid,
            provider.name,
            payload.username,
            str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    rec = store.create(user)
    _set_session_cookie(request, response, rec.session_id)

    logger.info(
        "LOGIN success | rid=%s | provider=%s | username=%s | sid=%s",
        rid,
        provider.name,
        user.username,
        rec.session_id,
    )

    return LoginResponse(session=rec.session_id, user=user)


# ------------------------------------------------------------------
# Keycloak
# ------------------------------------------------------------------
@router.get("/keycloak/login")
async def keycloak_login(request: Request):
    rid = getattr(request.state, "request_id", "-")

    if not settings.KEYCLOAK_ENABLED:
        raise HTTPException(status_code=409, detail="Keycloak disabled")

    st = kc_state_store.create()
    challenge = pkce_challenge(st.code_verifier)
    url = authorize_url(st.state, challenge)

    logger.info("KC login redirect | rid=%s | state=%s", rid, st.state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/keycloak/callback", response_model=KeycloakCallbackResponse)
async def keycloak_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
) -> KeycloakCallbackResponse:
    rid = getattr(request.state, "request_id", "-")

    if not settings.KEYCLOAK_ENABLED:
        raise HTTPException(status_code=409, detail="Keycloak disabled")

    logger.info("KC callback | rid=%s | state=%s", rid, state)

    try:
        user = await handle_callback(code=code, state=state)
        user.permissions = compute_permissions(user.roles)
    except Exception as e:
        logger.warning(
            "KC callback failed | rid=%s | state=%s | err=%s",
            rid,
            state,
            str(e),
        )
        raise HTTPException(status_code=401, detail="Keycloak login failed")

    rec = store.create(user)
    _set_session_cookie(request, response, rec.session_id)

    logger.info(
        "KC login success | rid=%s | username=%s | sid=%s",
        rid,
        user.username,
        rec.session_id,
    )

    return KeycloakCallbackResponse(session=rec.session_id, user=user)


# ------------------------------------------------------------------
# Session / user
# ------------------------------------------------------------------
@router.get("/me", response_model=UserInfo)
async def me(
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> UserInfo:
    rid = getattr(request.state, "request_id", "-")
    logger.debug(
        "ME | rid=%s | username=%s | source=%s",
        rid,
        user.username,
        user.auth_source,
    )
    return user


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
) -> LogoutResponse:
    rid = getattr(request.state, "request_id", "-")
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)

    if sid:
        store.delete(sid)

    _clear_session_cookie(request, response)

    logger.info("LOGOUT | rid=%s | sid=%s", rid, sid or "-")
    return LogoutResponse()


# ------------------------------------------------------------------
# Password management
# ------------------------------------------------------------------
@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> ChangePasswordResponse:
    rid = getattr(request.state, "request_id", "-")

    provider = choose_provider(user.auth_source)

    logger.info(
        "CHANGE_PASSWORD attempt | rid=%s | username=%s | source=%s",
        rid,
        user.username,
        user.auth_source,
    )

    try:
        await provider.change_password(
            user.username,
            payload.current_password,
            payload.new_password,
        )
    except NotImplementedError:
        raise HTTPException(
            status_code=409,
            detail=f"Password change not supported for provider '{provider.name}'",
        )
    except Exception as e:
        logger.warning(
            "CHANGE_PASSWORD failed | rid=%s | username=%s | err=%s",
            rid,
            user.username,
            str(e),
        )
        raise HTTPException(status_code=400, detail="Password change failed")

    logger.info(
        "CHANGE_PASSWORD success | rid=%s | username=%s",
        rid,
        user.username,
    )

    return ChangePasswordResponse()
