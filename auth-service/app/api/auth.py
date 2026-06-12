from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.internal_token import build_internal_headers
from app.core.errors import get_request_id
from app.core.logging import get_logger, log_event, mask_session_id
from app.core.deps import get_current_user
from app.core.internal_auth import require_internal_token
from app.core.principal_snapshot import issue_principal_snapshot_cookie_value

from app.services.providers.registry import (
    choose_provider,
    build_registry,
    ordered_providers,
)
from app.services.providers.base import (
    AuthUnavailable,
    InvalidCredentials,
    ProviderMisconfigured,
    SecretResolutionError,
)
from app.services.session_store import get_session_store
from app.services.identity_enrich import enrich_user_flags
from app.services.internal_clients import (
    IdentitySourceNotFound,
    dal_get,
    dal_get_identity_roles,
    dal_post,
    dal_resolve_login_identity,
    dal_resolve_ad_identity,
)

from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserInfo,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LogoutResponse,
    IntrospectRequest,
    IntrospectResponse,
)

settings = get_settings()
store = get_session_store()
logger = get_logger(__name__)
_runtime_logging_level = (settings.LOG_LEVEL or "INFO").upper()
_runtime_logging_retention_enabled = True
_runtime_logging_retention_days = 180

router = APIRouter(prefix="/auth", tags=["auth"])


class AdminChangePasswordRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    new_password: str = Field(..., min_length=1, max_length=512)
    current_password: str | None = Field(default=None, max_length=512)


def _request_id(request: Request) -> str:
    return str(get_request_id(request) or "-")


async def _load_logging_config_from_dal() -> dict[str, Any]:
    payload = await dal_get("/api/admin/config/advanced")
    raw = payload.get("data") if isinstance(payload, dict) else {}
    cfg = raw if isinstance(raw, dict) else {}
    logging_cfg = cfg.get("logging") if isinstance(cfg.get("logging"), dict) else {}

    level = _apply_runtime_log_level(str(logging_cfg.get("level") or _runtime_logging_level or "INFO"))
    try:
        retention_days = max(1, int(logging_cfg.get("retentionDays", _runtime_logging_retention_days or 180)))
    except Exception:
        retention_days = 180

    return {
        "level": level,
        "retentionEnabled": bool(logging_cfg.get("retentionEnabled", _runtime_logging_retention_enabled)),
        "retentionDays": retention_days,
    }


async def _save_logging_config_to_dal(*, level: str, retention_enabled: bool, retention_days: int) -> dict[str, Any]:
    await dal_post(
        "/api/admin/config/advanced",
        {
            "logging": {
                "level": level,
                "retentionEnabled": bool(retention_enabled),
                "retentionDays": max(1, int(retention_days)),
            }
        },
    )
    return {
        "level": level,
        "retentionEnabled": bool(retention_enabled),
        "retentionDays": max(1, int(retention_days)),
    }


async def _emit_activity_event(
    *,
    action: str,
    actor_type: str,
    actor_id: str | int | None,
    actor_display: str | None,
    target_type: str | None,
    target_id: str | int | None,
    target_display: str | None,
    metadata_json: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> None:
    url = settings.DAL_URL.rstrip("/") + "/api/activity/events"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        **build_internal_headers(correlation_id),
    }
    payload = {
        "action": action,
        "outcome": "success",
        "actor_type": actor_type,
        "actor_id": actor_id,
        "actor_display": actor_display,
        "target_type": target_type,
        "target_id": target_id,
        "target_display": target_display,
        "metadata_json": metadata_json or {},
        "correlation_id": correlation_id,
        "source_service": "auth-service",
    }
    try:
        async with httpx.AsyncClient(timeout=int(settings.DAL_TIMEOUT_SECONDS)) as client:
            await client.post(url, json=payload, headers=headers)
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_ACTIVITY_FORWARD_FAILED",
            action=action,
            outcome="error",
            message=str(exc),
        )


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


def _session_expires_at_iso(rec: object | None) -> str | None:
    if rec is None:
        return None
    created_at = getattr(rec, "created_at", None)
    last_seen = getattr(rec, "last_seen", None)
    if not isinstance(created_at, datetime) or not isinstance(last_seen, datetime):
        return None

    now = datetime.now(timezone.utc)
    hard_exp = created_at + timedelta(seconds=int(settings.SESSION_TTL_SECONDS))
    idle_exp = last_seen + timedelta(seconds=int(settings.SESSION_IDLE_TIMEOUT))
    exp = hard_exp if hard_exp <= idle_exp else idle_exp
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        exp = now
    return exp.isoformat()


def _extract_domain_hint(username: Optional[str]) -> Optional[str]:
    raw = (username or "").strip()
    if not raw:
        return None
    if "\\" in raw:
        domain = raw.split("\\", 1)[0].strip().lower().strip(".")
        return domain or None
    if "@" in raw:
        domain = raw.split("@", 1)[1].strip().lower().strip(".")
        return domain or None
    return None


def _normalize_login_input(username: Optional[str]) -> dict[str, str | None]:
    raw = (username or "").strip()
    if not raw:
        return {
            "login": None,
            "username": None,
            "domain_hint": None,
            "upn_hint": None,
        }
    if "\\" in raw:
        domain, user = raw.split("\\", 1)
        normalized_user = user.strip()
        return {
            "login": raw,
            "username": normalized_user or None,
            "domain_hint": domain.strip() or None,
            "upn_hint": None,
        }
    if "@" in raw:
        user, domain = raw.split("@", 1)
        normalized_user = user.strip()
        normalized_domain = domain.strip()
        upn = f"{normalized_user}@{normalized_domain}" if normalized_user and normalized_domain else raw
        return {
            "login": raw,
            "username": normalized_user or None,
            "domain_hint": normalized_domain or None,
            "upn_hint": upn,
        }
    return {
        "login": raw,
        "username": raw,
        "domain_hint": None,
        "upn_hint": None,
    }


def _choose_login_provider_name(explicit_provider: Optional[str], username: Optional[str]) -> str:
    explicit = (explicit_provider or "").strip().lower()
    if explicit:
        return explicit

    # Smart routing (modern UX):
    # - DOMAIN\\user or user@domain => AD
    # - plain username => local
    if _extract_domain_hint(username):
        return "ad"
    return "local"


# ============================================================
# Providers
# ============================================================

@router.get("/providers")
async def providers() -> dict:
    """
    List enabled authentication providers for UI selection.

    SECURITY:
    - Non-sensitive
    - Names only (no internal config leakage)
    """
    registry = build_registry()
    ordered = ordered_providers(registry)
    names = [p.name for p in ordered] if ordered else sorted(registry.keys())
    default_provider = (settings.DEFAULT_AUTH_PROVIDER or "").strip().lower()
    if default_provider not in names:
        default_provider = names[0] if names else "local"

    return {
        "default": default_provider,
        "enabled": names,
        "available": sorted(registry.keys()),
    }


# ============================================================
# Cookies helpers
# ============================================================

def _is_https_request(request: Request) -> bool:
    """
    Detect if the *client-facing* request is HTTPS.
    Works behind reverse proxies via X-Forwarded-Proto.
    """
    xf_proto = (
        request.headers.get("x-forwarded-proto", "")
        .split(",")[0]
        .strip()
        .lower()
    )
    if xf_proto:
        return xf_proto == "https"
    return request.url.scheme == "https"


def _cookie_domain() -> str | None:
    """Allow config to omit domain (recommended in dev)."""
    return settings.COOKIE_DOMAIN or None


def _cookie_samesite() -> str:
    """Normalize SameSite values for Starlette."""
    v = (settings.COOKIE_SAMESITE or "lax").lower()
    return v if v in {"lax", "strict", "none"} else "lax"


def _principal_cookie_samesite() -> str:
    v = (settings.PRINCIPAL_COOKIE_SAMESITE or "lax").lower()
    return v if v in {"lax", "strict", "none"} else "lax"


def _should_set_secure_cookie(request: Request) -> bool:
    """
    Final decision:
    - HTTP  -> secure=False
    - HTTPS -> secure=True
    """
    return _is_https_request(request)


def _principal_cookie_secure(request: Request) -> bool:
    if settings.PRINCIPAL_COOKIE_SECURE:
        return True
    return _is_https_request(request)


def _set_session_cookie(
    request: Request,
    response: Response,
    session_id: str,
) -> None:
    """
    Set session cookie with safe dev/prod behavior.

    RULES:
    - HttpOnly always
    - Secure only if HTTPS
    - SameSite=Lax by default
    - SameSite=None requires Secure
    """
    secure = _should_set_secure_cookie(request)
    samesite = _cookie_samesite()
    domain = _cookie_domain()

    if samesite == "none" and not secure:
        logger.warning(
            "[AUTH][COOKIE] SameSite=None requires Secure; "
            "downgrading to SameSite=Lax for HTTP/dev"
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


def _set_principal_cookie(
    request: Request,
    response: Response,
    user: UserInfo,
) -> None:
    secure = _principal_cookie_secure(request)
    samesite = _principal_cookie_samesite()
    domain = _cookie_domain()

    if samesite == "none" and not secure:
        logger.warning(
            "[AUTH][COOKIE] principal SameSite=None requires Secure; "
            "downgrading to SameSite=Lax for HTTP/dev"
        )
        samesite = "lax"

    value = issue_principal_snapshot_cookie_value(user)

    response.set_cookie(
        key=settings.PRINCIPAL_COOKIE_NAME,
        value=value,
        httponly=True,
        secure=secure,
        samesite=samesite,
        domain=domain,
        path="/",
        max_age=settings.PRINCIPAL_TTL_SECONDS,
    )


def _clear_principal_cookie(request: Request, response: Response) -> None:
    secure = _principal_cookie_secure(request)
    response.delete_cookie(
        key=settings.PRINCIPAL_COOKIE_NAME,
        domain=_cookie_domain(),
        path="/",
        samesite=_principal_cookie_samesite(),
        secure=secure,
    )


def _clear_session_cookie(request: Request, response: Response) -> None:
    """Clear session cookie (must match original attributes)."""
    secure = _should_set_secure_cookie(request)

    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        domain=_cookie_domain(),
        path="/",
        samesite=_cookie_samesite(),
        secure=secure,
    )


def _require_platform_admin(user: UserInfo) -> None:
    roles = [str(r) for r in (user.roles or [])]
    if "platform_admin" not in roles:
        raise _http_error(
            status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="platform_admin role required",
            details={"required_role": "platform_admin"},
        )


def _apply_runtime_log_level(level_name: str) -> str:
    normalized = str(level_name or "INFO").upper()
    if normalized == "WARN":
        normalized = "WARNING"

    allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
    if normalized not in allowed:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="Invalid log level",
            details={"allowed": ["DEBUG", "INFO", "WARN", "ERROR"]},
        )

    level = getattr(logging, normalized)
    logging.getLogger().setLevel(level)
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)
    logger.setLevel(level)

    return "WARN" if normalized == "WARNING" else normalized


# ============================================================
# Post-auth enrichment (SINGLE ENTRY POINT)
# ============================================================

async def _post_auth_enrich_user(user: UserInfo) -> UserInfo:
    """
    POST AUTH — SINGLE ENRICHMENT POINT (V1)

    RULES:
    - no roles/permissions computation
    - session stores FINAL UserInfo
    """
    return enrich_user_flags(user)


async def _attach_rbac_roles(user: UserInfo) -> UserInfo:
    """Attach effective RBAC roles (SQL-first) to the session user payload."""
    if not user.identity_id:
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="Authenticated principal missing identity_id",
            details={"stage": "attach_rbac_roles"},
        )

    try:
        data = await dal_get_identity_roles(user.identity_id)
    except IdentitySourceNotFound:
        raise _http_error(
            status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="Identity has no effective roles mapping",
            details={"identity_id": user.identity_id},
        )

    roles = data.get("roles") if isinstance(data, dict) else None
    if not isinstance(roles, list):
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_UNAVAILABLE",
            message="Roles service returned an invalid contract",
            details={"identity_id": user.identity_id},
        )
    user.roles = [str(x) for x in roles]
    normalized_roles = {str(x).strip().lower() for x in roles}
    user.is_admin = "platform_admin" in normalized_roles or "admin" in normalized_roles

    return user


async def _bind_ad_user_to_local_identity(user: UserInfo) -> UserInfo:
    """
    For AD-authenticated users, resolve the corresponding imported local identity.

    Contract:
    - AD authentication validates credentials against directory.
    - Access to BornToShare requires a local imported AD identity.
    """
    if (user.auth_source or "").strip().lower() != "ad":
        return user

    data = await dal_resolve_ad_identity(
        external_id=user.external_id,
        username=user.username,
        email=user.email,
        identity_source_id=user.identity_source_id,
    )

    if not bool((data or {}).get("found")):
        raise _http_error(
            status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="AD user is not imported in BornToShare",
        )

    if (data or {}).get("is_active") is False:
        raise _http_error(
            status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="Identity inactive",
        )

    identity_id = str((data or {}).get("identity_id") or "").strip()
    if not identity_id:
        raise _http_error(
            status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="AD identity mapping is invalid",
            details={"required_field": "identity_id"},
        )

    user.identity_id = identity_id
    user.display_name = user.display_name or (data or {}).get("display_name")
    user.email = user.email or (data or {}).get("email")
    return user


def _apply_resolved_identity(user: UserInfo, resolved_identity: dict[str, Any] | None) -> UserInfo:
    data = resolved_identity or {}
    identity_id = str(data.get("identity_id") or "").strip()
    if identity_id:
        user.identity_id = identity_id
    if not user.display_name:
        user.display_name = data.get("display_name")
    if not user.email:
        user.email = data.get("email")
    if not user.external_id:
        user.external_id = data.get("external_id")
    if data.get("source_id") is not None:
        try:
            user.identity_source_id = int(data.get("source_id"))
        except Exception:
            user.identity_source_id = user.identity_source_id
    user.auth_source = str(data.get("auth_source") or user.auth_source or "").strip().lower() or user.auth_source
    return user


def _ensure_identity_id(user: UserInfo) -> UserInfo:
    identity_id = str(user.identity_id or "").strip()
    if not identity_id:
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="Authenticated principal missing identity_id",
            details={"stage": "post_auth"},
        )
    user.identity_id = identity_id
    return user


async def _authenticate_login(payload: LoginRequest, request: Request) -> tuple[UserInfo, str, dict[str, Any] | None]:
    rid = _request_id(request)
    normalized_login = _normalize_login_input(payload.username)
    resolved_identity: dict[str, Any] | None = None

    try:
        resolved_identity = await dal_resolve_login_identity(
            login=normalized_login.get("login"),
            username=normalized_login.get("username"),
            upn_hint=normalized_login.get("upn_hint"),
            domain_hint=normalized_login.get("domain_hint"),
        )
    except IdentitySourceNotFound:
        resolved_identity = None

    requested_provider = ""
    if bool((resolved_identity or {}).get("found")):
        is_active = bool((resolved_identity or {}).get("is_active"))
        status_value = str((resolved_identity or {}).get("status") or "").strip().lower()
        if not is_active or status_value == "inactive":
            log_event(
                logger,
                logging.WARNING,
                "AUTH_LOGIN_FAILED",
                request_id=rid,
                actor=payload.username,
                provider=str((resolved_identity or {}).get("auth_source") or "unknown"),
                outcome="identity_inactive",
                status_code=403,
                error_code="FORBIDDEN",
            )
            raise _http_error(
                status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="Invalid credentials",
            )

        requested_provider = str((resolved_identity or {}).get("auth_source") or "").strip().lower()
        log_event(
            logger,
            logging.INFO,
            "AUTH_PROVIDER_RESOLVED",
            request_id=rid,
            actor=normalized_login.get("username") or payload.username,
            provider=requested_provider,
            source_id=(resolved_identity or {}).get("source_id"),
            outcome="success",
        )
    else:
        requested_provider = _choose_login_provider_name(None, payload.username)
        if requested_provider == "ad":
            log_event(
                logger,
                logging.WARNING,
                "AUTH_LOGIN_FAILED",
                request_id=rid,
                actor=payload.username,
                provider="ad",
                outcome="identity_not_authorized",
                status_code=401,
                error_code="UNAUTHENTICATED",
            )
            raise _http_error(
                status.HTTP_401_UNAUTHORIZED,
                code="UNAUTHENTICATED",
                message="Invalid credentials",
            )

    try:
        provider = choose_provider(requested_provider)
    except ValueError:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message=f"Unknown or disabled auth provider '{requested_provider}'",
            details={"provider": requested_provider},
        )

    log_event(
        logger,
        logging.INFO,
        "AUTH_LOGIN_ATTEMPT",
        request_id=rid,
        actor=payload.username,
        provider=provider.name,
        outcome="attempt",
    )

    try:
        if (
            requested_provider == "ad"
            and bool((resolved_identity or {}).get("found"))
            and (resolved_identity or {}).get("source_id") is not None
            and hasattr(provider, "authenticate_for_source")
        ):
            user = await provider.authenticate_for_source(
                source_id=int((resolved_identity or {}).get("source_id")),
                username=payload.username,
                password=payload.password,
            )
        else:
            user = await provider.authenticate(payload.username, payload.password)
    except InvalidCredentials:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_LOGIN_FAILED",
            request_id=rid,
            actor=payload.username,
            provider=provider.name,
            outcome="invalid_credentials",
            status_code=401,
            error_code="UNAUTHENTICATED",
        )
        raise _http_error(
            status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHENTICATED",
            message="Invalid credentials",
        )
    except ProviderMisconfigured as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_MISCONFIGURED",
            request_id=rid,
            actor=payload.username,
            provider=provider.name,
            outcome="misconfigured",
            status_code=500,
            error_code="PROVIDER_MISCONFIGURED",
            message=str(exc),
        )
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="PROVIDER_MISCONFIGURED",
            message="Authentication provider misconfigured",
            details={"provider": provider.name},
        )
    except SecretResolutionError as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_SECRET_RESOLUTION_FAILED",
            request_id=rid,
            actor=payload.username,
            provider=provider.name,
            outcome="secret_resolution_failed",
            status_code=503,
            error_code="AUTH_UNAVAILABLE",
            message=str(exc),
        )
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_UNAVAILABLE",
            message="Authentication provider unavailable",
            details={"provider": provider.name},
        )
    except AuthUnavailable as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            request_id=rid,
            actor=payload.username,
            provider=provider.name,
            outcome="unavailable",
            status_code=503,
            error_code="AUTH_UNAVAILABLE",
            message=str(exc),
        )
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_UNAVAILABLE",
            message="Authentication provider unavailable",
            details={"provider": provider.name},
        )

    if user is None:
        raise _http_error(
            status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHENTICATED",
            message="Invalid credentials",
        )

    if bool((resolved_identity or {}).get("found")):
        user = _apply_resolved_identity(user, resolved_identity)

    return user, provider.name, resolved_identity


# ============================================================
# Auth endpoints
# ============================================================

@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    rid = _request_id(request)
    user, provider_name, resolved_identity = await _authenticate_login(payload, request)

    if provider_name == "ad":
        if bool((resolved_identity or {}).get("found")):
            user = _apply_resolved_identity(user, resolved_identity)
        else:
            user = await _bind_ad_user_to_local_identity(user)

    # Post-auth enrichment (keep if it does NOT add IAM / roles / permissions)
    user = await _post_auth_enrich_user(user)
    user = _ensure_identity_id(user)

    # RBAC roles snapshot: SQL is source of truth
    user = await _attach_rbac_roles(user)

    # Create session
    rec = store.create(user)
    _set_session_cookie(request, response, rec.session_id)
    _set_principal_cookie(request, response, user)

    log_event(
        logger,
        logging.INFO,
        "AUTH_SESSION_CREATED",
        request_id=rid,
        actor=user.username,
        provider=provider_name,
        session_id=mask_session_id(rec.session_id),
        outcome="success",
    )
    log_event(
        logger,
        logging.INFO,
        "AUTH_LOGIN_SUCCESS",
        request_id=rid,
        actor=user.username,
        provider=provider_name,
        outcome="success",
    )
    await _emit_activity_event(
        action="auth.login",
        actor_type="user",
        actor_id=user.identity_id,
        actor_display=user.display_name or user.username,
        target_type="identity",
        target_id=user.identity_id,
        target_display=user.display_name or user.username,
        metadata_json={"provider": provider_name, "auth_source": user.auth_source},
        correlation_id=rid,
    )

    return LoginResponse(user=user)


# ============================================================
# Introspection (internal) — used by internal callers for RBAC/session checks
# ============================================================


@router.post("/internal/introspect", response_model=IntrospectResponse)
async def introspect(
    payload: IntrospectRequest,
    request: Request,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
) -> IntrospectResponse:
    require_internal_token(x_internal_token, source="auth.introspect")
    rid = _request_id(request)
    rec = store.get(payload.session)
    if not rec:
        log_event(
            logger,
            logging.INFO,
            "AUTH_INTERNAL_INTROSPECT",
            request_id=rid,
            session_id=mask_session_id(payload.session),
            outcome="inactive",
        )
        return IntrospectResponse(
            active=False,
            authenticated=False,
            session_status="inactive",
            identity_id=None,
            user=None,
            auth_source=None,
            expires_at=None,
            roles=[],
        )

    user = getattr(rec, "user", None)
    roles = getattr(user, "roles", []) if user else []
    log_event(
        logger,
        logging.INFO,
        "AUTH_INTERNAL_INTROSPECT",
        request_id=rid,
        session_id=mask_session_id(payload.session),
        actor=getattr(user, "username", None),
        outcome="active",
    )
    return IntrospectResponse(
        active=True,
        authenticated=True,
        session_status="active",
        identity_id=getattr(user, "identity_id", None),
        user=user,
        auth_source=getattr(user, "auth_source", None),
        expires_at=_session_expires_at_iso(rec),
        roles=[str(r) for r in (roles or [])],
    )

# ============================================================
# Session / user
# ============================================================

@router.get("/me", response_model=UserInfo)
async def me(
    request: Request,
    response: Response,
    user: UserInfo = Depends(get_current_user),
) -> UserInfo:
    """
    READ-ONLY endpoint.

    RULE:
    - return session user AS-IS
    - no enrichment
    - no recomputation
    """
    _set_principal_cookie(request, response, user)
    log_event(
        logger,
        logging.INFO,
        "AUTH_ME_SUCCESS",
        request_id=_request_id(request),
        actor=user.username,
        outcome="success",
    )
    return user


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
) -> LogoutResponse:
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
    rid = _request_id(request)
    session_user = None

    if sid:
        rec = store.get(sid)
        session_user = getattr(rec, "user", None) if rec else None
        store.delete(sid)
        log_event(
            logger,
            logging.INFO,
            "AUTH_SESSION_REVOKED",
            request_id=rid,
            session_id=mask_session_id(sid),
            outcome="success",
        )

    _clear_session_cookie(request, response)
    _clear_principal_cookie(request, response)
    log_event(
        logger,
        logging.INFO,
        "AUTH_LOGOUT",
        request_id=rid,
        session_id=mask_session_id(sid),
        outcome="success",
    )
    await _emit_activity_event(
        action="auth.logout",
        actor_type="user",
        actor_id=getattr(session_user, "identity_id", None),
        actor_display=getattr(session_user, "display_name", None) or getattr(session_user, "username", None),
        target_type="identity",
        target_id=getattr(session_user, "identity_id", None),
        target_display=getattr(session_user, "display_name", None) or getattr(session_user, "username", None),
        metadata_json={},
        correlation_id=rid,
    )

    return LogoutResponse()


# ============================================================
# Admin — Sessions
# ============================================================


@router.get("/admin/sessions")
async def list_admin_sessions(request: Request, user: UserInfo = Depends(get_current_user)) -> dict:
    _require_platform_admin(user)

    sessions = []
    for rec in store.list():
        session_user = getattr(rec, "user", None)
        sessions.append(
            {
                "id": rec.session_id,
                "id_masked": mask_session_id(rec.session_id),
                "user": getattr(session_user, "username", "unknown"),
                "roles": list(getattr(session_user, "roles", []) or []),
                "status": "active",
                "created_at": rec.created_at.isoformat(),
                "last_seen": rec.last_seen.isoformat(),
                "auth_source": getattr(session_user, "auth_source", None),
                "is_admin": "platform_admin" in list(getattr(session_user, "roles", []) or []),
            }
        )

    sessions.sort(key=lambda s: s.get("last_seen", ""), reverse=True)
    log_event(
        logger,
        logging.INFO,
        "AUTH_ADMIN_SESSIONS_LIST",
        request_id=_request_id(request),
        actor=user.username,
        outcome="success",
        count=len(sessions),
    )
    return {"sessions": sessions}


@router.delete("/admin/sessions/{session_id}")
async def revoke_admin_session(
    request: Request,
    session_id: str,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    _require_platform_admin(user)
    store.delete(session_id)
    log_event(
        logger,
        logging.INFO,
        "AUTH_ADMIN_SESSIONS_REVOKE",
        request_id=_request_id(request),
        actor=user.username,
        target=mask_session_id(session_id),
        outcome="success",
    )
    return {"ok": True, "message": "Session revoked"}


# ============================================================
# Admin — Logging
# ============================================================


@router.get("/admin/logging")
async def get_admin_logging_config(user: UserInfo = Depends(get_current_user)) -> dict:
    global _runtime_logging_level, _runtime_logging_retention_enabled, _runtime_logging_retention_days
    _require_platform_admin(user)
    try:
        cfg = await _load_logging_config_from_dal()
    except AuthUnavailable:
        cfg = {
            "level": _runtime_logging_level,
            "retentionEnabled": _runtime_logging_retention_enabled,
            "retentionDays": _runtime_logging_retention_days,
        }
    _runtime_logging_level = str(cfg.get("level") or _runtime_logging_level)
    _runtime_logging_retention_enabled = bool(cfg.get("retentionEnabled", _runtime_logging_retention_enabled))
    _runtime_logging_retention_days = max(1, int(cfg.get("retentionDays", _runtime_logging_retention_days or 180)))
    return cfg


@router.put("/admin/logging")
async def set_admin_logging_config(payload: dict[str, Any], user: UserInfo = Depends(get_current_user)) -> dict:
    global _runtime_logging_level, _runtime_logging_retention_enabled, _runtime_logging_retention_days
    _require_platform_admin(user)

    level = _apply_runtime_log_level(str(payload.get("level", "INFO")))
    try:
        retention_days = max(1, int(payload.get("retentionDays", _runtime_logging_retention_days)))
    except Exception:
        retention_days = 180
    retention_enabled = bool(payload.get("retentionEnabled", _runtime_logging_retention_enabled))

    try:
        cfg = await _save_logging_config_to_dal(
            level=level,
            retention_enabled=retention_enabled,
            retention_days=retention_days,
        )
    except AuthUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    _runtime_logging_level = str(cfg.get("level") or level)
    _runtime_logging_retention_enabled = bool(cfg.get("retentionEnabled", retention_enabled))
    _runtime_logging_retention_days = max(1, int(cfg.get("retentionDays", retention_days)))
    log_event(
        logger,
        logging.INFO,
        "AUTH_ADMIN_LOGGING_UPDATED",
        actor=user.username,
        target=_runtime_logging_level,
        outcome="success",
    )

    return {
        "ok": True,
        "message": "Logging level updated",
        "level": _runtime_logging_level,
        "retentionEnabled": _runtime_logging_retention_enabled,
        "retentionDays": _runtime_logging_retention_days,
    }


@router.post("/admin/logs/purge")
async def purge_admin_logs(user: UserInfo = Depends(get_current_user)) -> dict:
    _require_platform_admin(user)

    log_event(
        logger,
        logging.WARNING,
        "AUTH_ADMIN_LOGS_PURGE_REQUESTED",
        actor=user.username,
        outcome="noop",
    )
    return {"ok": True, "message": "Purge action accepted"}




# ============================================================
# Password management
# ============================================================

@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    user: UserInfo = Depends(get_current_user),
) -> ChangePasswordResponse:
    provider = choose_provider(user.auth_source)
    rid = _request_id(request)

    log_event(
        logger,
        logging.INFO,
        "AUTH_CHANGE_PASSWORD_ATTEMPT",
        request_id=rid,
        actor=user.username,
        provider=user.auth_source,
        outcome="attempt",
    )

    try:
        await provider.change_password(
            user.username,
            payload.current_password,
            payload.new_password,
        )
    except NotImplementedError:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            code="CONFLICT",
            message=f"Password change not supported for provider '{provider.name}'",
            details={"provider": provider.name},
        )
    except InvalidCredentials:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_CHANGE_PASSWORD_FAILED",
            request_id=rid,
            actor=user.username,
            provider=user.auth_source,
            outcome="invalid_credentials",
            status_code=400,
            error_code="BAD_REQUEST",
        )
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="Password change failed",
        )
    except ProviderMisconfigured as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_MISCONFIGURED",
            request_id=rid,
            actor=user.username,
            provider=user.auth_source,
            outcome="misconfigured",
            status_code=500,
            error_code="PROVIDER_MISCONFIGURED",
            message=str(exc),
        )
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="PROVIDER_MISCONFIGURED",
            message="Authentication provider misconfigured",
            details={"provider": provider.name},
        )
    except SecretResolutionError as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_SECRET_RESOLUTION_FAILED",
            request_id=rid,
            actor=user.username,
            provider=user.auth_source,
            outcome="secret_resolution_failed",
            status_code=503,
            error_code="AUTH_UNAVAILABLE",
            message=str(exc),
        )
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_UNAVAILABLE",
            message="Authentication provider unavailable",
            details={"provider": provider.name},
        )
    except AuthUnavailable as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            request_id=rid,
            actor=user.username,
            provider=user.auth_source,
            outcome="unavailable",
            status_code=503,
            error_code="AUTH_UNAVAILABLE",
            message=str(exc),
        )
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_UNAVAILABLE",
            message="Authentication provider unavailable",
            details={"provider": provider.name},
        )

    log_event(
        logger,
        logging.INFO,
        "AUTH_CHANGE_PASSWORD_SUCCESS",
        request_id=rid,
        actor=user.username,
        provider=user.auth_source,
        outcome="success",
    )
    return ChangePasswordResponse()


@router.post("/admin/change-password", response_model=ChangePasswordResponse)
async def admin_change_password(
    request: Request,
    payload: AdminChangePasswordRequest,
    user: UserInfo = Depends(get_current_user),
) -> ChangePasswordResponse:
    _require_platform_admin(user)
    rid = _request_id(request)
    url = settings.DAL_URL.rstrip("/") + settings.DAL_CHANGE_PASSWORD_PATH
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        **build_internal_headers(rid),
    }
    if user.identity_id:
        headers["X-Identity-Id"] = str(user.identity_id)
    if user.display_name or user.username:
        headers["X-Actor-Display"] = str(user.display_name or user.username)

    try:
        async with httpx.AsyncClient(timeout=int(settings.DAL_TIMEOUT_SECONDS)) as client:
            response = await client.post(
                url,
                json={
                    "username": payload.username,
                    "current_password": payload.current_password,
                    "new_password": payload.new_password,
                },
                headers=headers,
            )
    except Exception as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_UNAVAILABLE",
            message="Password change backend unavailable",
            details={"error": str(exc)},
        )

    if response.status_code != status.HTTP_200_OK:
        backend_detail: Any
        try:
            backend_detail = response.json()
        except Exception:
            backend_detail = response.text
        raise _http_error(
            response.status_code,
            code="BAD_REQUEST" if response.status_code < 500 else "AUTH_UNAVAILABLE",
            message="Password change failed",
            details={"backend": backend_detail},
        )

    log_event(
        logger,
        logging.INFO,
        "AUTH_ADMIN_CHANGE_PASSWORD_SUCCESS",
        request_id=rid,
        actor=user.username,
        target=payload.username,
        outcome="success",
    )
    return ChangePasswordResponse()
