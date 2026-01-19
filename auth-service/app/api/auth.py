# app/api/auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.providers.registry import choose_provider, build_registry, ordered_providers
from app.core.providers.base import InvalidCredentials, AuthUnavailable
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
    """
    List enabled authentication providers for UI selection.

    SECURITY:
    - Keep this endpoint non-sensitive: do not reveal internal provider config.
    - Only returns names.
    """
    registry = build_registry()
    ordered = ordered_providers(registry)
    names = [p.name for p in ordered] if ordered else sorted(registry.keys())
    return {
        "default": settings.DEFAULT_AUTH_PROVIDER,
        "enabled": names,
        "available": sorted(registry.keys()),
        "keycloak_enabled": bool(getattr(settings, "KEYCLOAK_ENABLED", False)),
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
    """
    Set session cookie with safe dev/prod behavior.

    SECURITY:
    - HttpOnly prevents JS access
    - Secure is enabled only when HTTPS is detected
    - SameSite defaults to Lax
    - If SameSite=None then Secure must be true (browser requirement)
    """
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
# Shared post-auth hardening
# ------------------------------------------------------------------
async def _post_auth_enrich_user(user: UserInfo) -> UserInfo:
    """
    POST AUTH — STRICT DAL ROLES

    RULE:
    - roles come from DAL / provider
    - no fallback
    - no governance
    """
    roles = user.roles or []
    if not roles:
        logger.error(
            "[AUTH][ROLE] roles missing from provider/DAL",
            extra={
                "username": user.username,
                "source": user.auth_source,
            },
        )
        raise RuntimeError("Roles missing from DAL")

    # Defensive: remove empty/None and normalize to strings
    roles = [str(r).strip() for r in roles if str(r).strip()]
    if not roles:
        logger.error(
            "[AUTH][ROLE] roles empty after normalization",
            extra={
                "username": user.username,
                "source": user.auth_source,
            },
        )
        raise RuntimeError("Roles missing from DAL")

    user.roles = roles
    user.permissions = compute_permissions(user.roles)
    return user


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

    registry = build_registry()
    if payload.provider:
        # SECURITY: don't leak whether provider exists via different errors
        providers_to_try = [choose_provider(payload.provider)]
    else:
        ordered = ordered_providers(registry)
        providers_to_try = ordered if ordered else [choose_provider(settings.DEFAULT_AUTH_PROVIDER)]

    user: UserInfo | None = None
    last_err: str | None = None

    # SECURITY: do not log passwords; username is okay (but can be considered PII)
    # If you want stricter logs, you can hash/obfuscate username here.
    for provider in providers_to_try:
        logger.info(
            "LOGIN attempt | rid=%s | provider=%s | username=%s",
            rid,
            provider.name,
            payload.username,
        )

        try:
            user = await provider.authenticate(payload.username, payload.password)
            # Success -> stop on first successful provider
            break
        except InvalidCredentials as e:
            last_err = str(e) or "Invalid credentials"
            logger.warning(
                "LOGIN invalid | rid=%s | provider=%s | username=%s",
                rid,
                provider.name,
                payload.username,
            )
            continue
        except AuthUnavailable as e:
            last_err = str(e) or "Provider unavailable"
            logger.warning(
                "LOGIN provider unavailable | rid=%s | provider=%s | username=%s | err=%s",
                rid,
                provider.name,
                payload.username,
                last_err,
            )
            continue
        except Exception as e:
            # SECURITY: don't leak internals to client; log server-side
            last_err = str(e)
            logger.warning(
                "LOGIN failed | rid=%s | provider=%s | username=%s | err=%s",
                rid,
                provider.name,
                payload.username,
                last_err,
            )
            continue

    if user is None:
        # SECURITY: generic message
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Normalize roles/permissions exactly like Keycloak flow
    user = await _post_auth_enrich_user(user)

    rec = store.create(user)
    _set_session_cookie(request, response, rec.session_id)

    logger.info(
        "LOGIN success | rid=%s | provider=%s | username=%s | roles=%s | sid=%s",
        rid,
        user.auth_source,
        user.username,
        ",".join(user.roles or []),
        rec.session_id,
    )

    return LoginResponse(session=rec.session_id, user=user)


# ------------------------------------------------------------------
# Keycloak
# ------------------------------------------------------------------
@router.get("/keycloak/login")
async def keycloak_login(request: Request):
    rid = getattr(request.state, "request_id", "-")

    if not getattr(settings, "KEYCLOAK_ENABLED", False):
        raise HTTPException(status_code=409, detail="Keycloak disabled")

    st = kc_state_store.create()
    challenge = pkce_challenge(st.code_verifier)
    url = authorize_url(st.state, challenge)

    # SECURITY: state is not secret but avoid spraying it to logs at high volume if you prefer.
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

    if not getattr(settings, "KEYCLOAK_ENABLED", False):
        raise HTTPException(status_code=409, detail="Keycloak disabled")

    logger.info("KC callback | rid=%s | state=%s", rid, state)

    try:
        # handle_callback() must validate state, exchange code, and build UserInfo
        user = await handle_callback(code=code, state=state)

        # Normalize roles/permissions exactly like /login flow
        user = await _post_auth_enrich_user(user)
    except Exception as e:
        # SECURITY: keep generic client message
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
