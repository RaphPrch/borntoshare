from __future__ import annotations

import asyncio
from dataclasses import dataclass
import struct
import uuid
import logging

from app.services.secret_broker_client import resolve_secret

from app.core.config import get_settings
from app.core.logging import get_logger, log_event
from app.services.providers.base import (
    AuthProvider,
    AuthUnavailable,
    InvalidCredentials,
    ProviderMisconfigured,
    SecretResolutionError,
)
from app.services.internal_clients import (
    dal_get_identity_source_by_id,
    dal_get_active_identity_source,
    dal_get_active_identity_source_by_domain,
    IdentitySourceNotFound,
)
from app.schemas.auth import UserInfo

settings = get_settings()
logger = get_logger(__name__)

try:
    # Optional dependency
    from ldap3 import Connection, Server, ALL, SUBTREE  # type: ignore
except ImportError:  # pragma: no cover
    Connection = None  # type: ignore
    Server = None  # type: ignore
    ALL = None  # type: ignore
    SUBTREE = None  # type: ignore


def _format_object_guid(value) -> str | None:
    """Normalize AD objectGUID to canonical UUID string.

    ldap3 may return bytes (little-endian), uuid.UUID, or a string.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        v = value.strip()
        return v or None
    if isinstance(value, (bytes, bytearray)):
        b = bytes(value)
        # AD objectGUID is stored little-endian for first 3 components
        try:
            return str(uuid.UUID(bytes_le=b))
        except (ValueError, TypeError):
            return None
    return None


def _format_object_sid(value) -> str | None:
    """Normalize AD objectSid to S-1-... string."""
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        return v or None
    if isinstance(value, (bytes, bytearray)):
        b = bytes(value)
        if len(b) < 8:
            return None

        revision = b[0]
        subauth_count = b[1]
        ident_auth = int.from_bytes(b[2:8], byteorder="big", signed=False)
        # Each subauthority is a 32-bit little-endian unsigned int
        expected_len = 8 + 4 * subauth_count
        if len(b) < expected_len:
            return None

        subauths: list[int] = []
        for i in range(subauth_count):
            start = 8 + (4 * i)
            subauths.append(struct.unpack("<I", b[start : start + 4])[0])

        return "S-{}-{}{}".format(
            revision,
            ident_auth,
            "".join(f"-{x}" for x in subauths),
        )

    return None


def _split_username(raw: str) -> tuple[str, str | None, str | None]:
    value = (raw or "").strip()
    if "\\" in value:
        domain, user = value.split("\\", 1)
        return user, domain or None, None
    if "@" in value:
        user, domain = value.split("@", 1)
        return user, None, domain or None
    return value, None, None


@dataclass
class ADConfig:
    source_id: int | None
    url: str
    base_dn: str
    user_filter: str
    bind_user: str
    bind_password: str
    user_dn_template: str


@dataclass
class _ADSearchResult:
    user_dn: str
    display_name: str | None
    email: str | None
    upn: str | None
    object_guid: str | None
    object_sid: str | None
    disabled: bool


def _entry_attr_value(entry, attr_name: str):
    attr = getattr(entry, attr_name, None)
    if attr is None:
        return None
    return getattr(attr, "value", None)


def _coerce_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ad_account_disabled(*, user_account_control, computed_control) -> bool:
    disabled_flag = 0x2
    computed_disabled_flag = 0x10

    uac = _coerce_int(user_account_control)
    if uac is not None and (uac & disabled_flag):
        return True

    computed = _coerce_int(computed_control)
    if computed is not None and (computed & computed_disabled_flag):
        return True

    return False


def _build_search_filters(*, username: str, raw_username: str) -> list[str]:
    normalized = str(username or "").strip()
    raw = str(raw_username or "").strip()
    filters: list[str] = []

    if normalized:
        filters.append(f"(sAMAccountName={normalized})")
    if raw and "@" in raw:
        filters.append(f"(userPrincipalName={raw})")
    elif normalized and "@" in normalized:
        filters.append(f"(userPrincipalName={normalized})")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in filters:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def _build_ad_config(src: dict, *, target: str | None) -> ADConfig:
    protocol = (src.get("protocol") or "ldaps").lower()
    host = (src.get("host") or "").strip()
    port = int(src.get("port") or (636 if protocol == "ldaps" else 389))

    if not bool(src.get("auth_enabled", False)):
        raise ProviderMisconfigured("AD identity source is not auth-enabled")

    if not host:
        raise ProviderMisconfigured("AD identity source missing host")

    url = f"{protocol}://{host}:{port}"
    bind_password = _resolve_bind_password(src, target=target)

    return ADConfig(
        source_id=int(src.get("id") or 0) or None,
        url=url,
        base_dn=str(src.get("base_dn") or ""),
        user_filter=settings.AD_USER_FILTER,
        bind_user=str(src.get("bind_dn") or ""),
        bind_password=bind_password,
        user_dn_template=settings.AD_USER_DN_TEMPLATE,
    )


async def _load_active_config() -> ADConfig | None:
    """Load AD identity source from DAL."""
    try:
        src = await dal_get_active_identity_source("ad")
    except IdentitySourceNotFound:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_PROVIDER_AD_BIND_FAILED",
            provider="ad",
            outcome="identity_source_not_found",
            error_code="NOT_FOUND",
        )
        return None
    except AuthUnavailable as e:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="ad",
            outcome="identity_source_resolution_failed",
            error_code="INTERNAL_ERROR",
            message=str(e),
        )
        raise AuthUnavailable("Identity source resolution failed") from e

    return _build_ad_config(src, target=None)


async def _load_active_config_for_domain(domain_hint: str | None) -> ADConfig | None:
    domain = str(domain_hint or "").strip().lower().strip(".")
    if not domain:
        return await _load_active_config()

    try:
        src = await dal_get_active_identity_source_by_domain("ad", domain)
    except IdentitySourceNotFound:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_PROVIDER_AD_BIND_FAILED",
            provider="ad",
            target=domain,
            outcome="identity_source_not_found",
            error_code="NOT_FOUND",
        )
        return None
    except AuthUnavailable as e:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="ad",
            target=domain,
            outcome="identity_source_resolution_failed",
            error_code="INTERNAL_ERROR",
            message=str(e),
        )
        raise AuthUnavailable("Identity source resolution failed") from e

    return _build_ad_config(src, target=domain)


async def _load_active_config_for_source(source_id: int) -> ADConfig | None:
    try:
        src = await dal_get_identity_source_by_id(int(source_id))
    except IdentitySourceNotFound:
        log_event(
            logger,
            logging.WARNING,
            "AUTH_PROVIDER_AD_BIND_FAILED",
            provider="ad",
            target=str(source_id),
            outcome="identity_source_not_found",
            error_code="NOT_FOUND",
        )
        return None
    except AuthUnavailable as e:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_UNAVAILABLE",
            provider="ad",
            target=str(source_id),
            outcome="identity_source_resolution_failed",
            error_code="INTERNAL_ERROR",
            message=str(e),
        )
        raise AuthUnavailable("Identity source resolution failed") from e

    return _build_ad_config(src, target=str(source_id))


class ADLDAPProvider(AuthProvider):
    """Authenticate a user against AD/LDAP.

    V1 goals:
    - AD is OPTIONAL
    - No implicit fallback to another provider in this layer
    - Secrets are resolved ONLY via Secret Broker
    """

    name = "ad"

    def __init__(self) -> None:
        if not settings.AD_ENABLED:
            log_event(
                logger,
                logging.WARNING,
                "AUTH_PROVIDER_UNAVAILABLE",
                provider="ad",
                outcome="disabled",
                error_code="INTERNAL_ERROR",
            )

    async def _authenticate_sync(self, cfg: ADConfig, username: str, password: str) -> UserInfo:
        return await asyncio.to_thread(self._authenticate_blocking, cfg, username, password)

    def _build_server(self, cfg: ADConfig):
        return Server(cfg.url, get_info=ALL, connect_timeout=settings.AD_CONNECT_TIMEOUT_SECONDS)

    def _search_user(self, cfg: ADConfig, server, raw_username: str, normalized_user: str) -> _ADSearchResult | None:
        if not (cfg.bind_user and cfg.bind_password):
            return None

        with Connection(
            server,
            user=cfg.bind_user,
            password=cfg.bind_password,
            auto_bind=True,
        ) as search_conn:
            attrs = [
                "distinguishedName",
                "displayName",
                "mail",
                "userPrincipalName",
                "objectGUID",
                "objectSid",
                "userAccountControl",
                "msDS-User-Account-Control-Computed",
            ]
            filters = _build_search_filters(username=normalized_user, raw_username=raw_username)
            if not filters:
                return None

            for flt in filters:
                ok = search_conn.search(
                    search_base=cfg.base_dn,
                    search_filter=flt,
                    search_scope=SUBTREE,
                    attributes=attrs,
                    size_limit=1,
                )
                if not ok or not search_conn.entries:
                    continue

                entry = search_conn.entries[0]
                user_dn = str(_entry_attr_value(entry, "distinguishedName") or "").strip()
                if not user_dn:
                    continue

                return _ADSearchResult(
                    user_dn=user_dn,
                    display_name=str(_entry_attr_value(entry, "displayName") or "") or None,
                    email=str(_entry_attr_value(entry, "mail") or "") or None,
                    upn=str(_entry_attr_value(entry, "userPrincipalName") or "") or None,
                    object_guid=_format_object_guid(_entry_attr_value(entry, "objectGUID")),
                    object_sid=_format_object_sid(_entry_attr_value(entry, "objectSid")),
                    disabled=_ad_account_disabled(
                        user_account_control=_entry_attr_value(entry, "userAccountControl"),
                        computed_control=_entry_attr_value(entry, "msDS-User-Account-Control-Computed"),
                    ),
                )
            return None

    def _authenticate_blocking(self, cfg: ADConfig, username: str, password: str) -> UserInfo:
        normalized_user, domain, upn_domain = _split_username(username)
        server = self._build_server(cfg)

        # Mode 2: direct user bind with DN template.
        if cfg.user_dn_template:
            user_dn = cfg.user_dn_template.format(
                username=normalized_user,
                domain=domain or "",
                upn_domain=upn_domain or "",
            )

            with Connection(server, user=user_dn, password=password, auto_bind=True):
                pass

            display_name = None
            email = None
            external_id = user_dn

            found = self._search_user(cfg, server, username, normalized_user)
            if found:
                if found.disabled:
                    raise InvalidCredentials("Invalid credentials")
                display_name = found.display_name
                email = found.email
                external_id = found.object_guid or found.object_sid or found.user_dn

            return UserInfo(
                identity_id=None,
                identity_source_id=cfg.source_id,
                username=normalized_user,
                display_name=display_name,
                email=email,
                external_id=external_id,
                auth_source="ad",
            )

        # Mode 1: service bind + search DN + user bind.
        if not (cfg.bind_user and cfg.bind_password):
            raise ProviderMisconfigured(
                "AD bind account not configured (set bind_dn/bind_password or user_dn_template)"
            )

        found = self._search_user(cfg, server, username, normalized_user)
        if not found:
            raise InvalidCredentials("Invalid credentials")
        if found.disabled:
            raise InvalidCredentials("Invalid credentials")

        with Connection(server, user=found.user_dn, password=password, auto_bind=True):
            pass

        return UserInfo(
            identity_id=None,
            identity_source_id=cfg.source_id,
            username=normalized_user,
            display_name=found.display_name,
            email=found.email,
            external_id=found.object_guid or found.object_sid or found.user_dn,
            auth_source="ad",
        )

    async def authenticate(self, username: str, password: str) -> UserInfo:
        if not settings.AD_ENABLED:
            raise AuthUnavailable("AD/LDAP authentication is disabled")

        if Connection is None or Server is None:
            raise AuthUnavailable("ldap3 is not installed in auth-service")

        if not username or not password:
            raise InvalidCredentials("Invalid credentials")

        _, domain, upn_domain = _split_username(username)
        domain_hint = domain or upn_domain
        log_event(
            logger,
            logging.INFO,
            "AUTH_PROVIDER_AD_BIND_ATTEMPT",
            provider="ad",
            actor=username,
            target=domain_hint,
            outcome="attempt",
        )

        active_cfg = await _load_active_config_for_domain(domain_hint)
        if not active_cfg:
            raise ProviderMisconfigured("No AD identity source configured")

        try:
            user = await self._authenticate_sync(active_cfg, username, password)
        except InvalidCredentials:
            log_event(
                logger,
                logging.WARNING,
                "AUTH_PROVIDER_AD_BIND_FAILED",
                provider="ad",
                actor=username,
                target=domain_hint,
                outcome="invalid_credentials",
                error_code="UNAUTHENTICATED",
            )
            raise
        except ProviderMisconfigured:
            raise
        except SecretResolutionError:
            raise
        except AuthUnavailable:
            log_event(
                logger,
                logging.ERROR,
                "AUTH_PROVIDER_UNAVAILABLE",
                provider="ad",
                actor=username,
                target=domain_hint,
                outcome="unavailable",
                error_code="INTERNAL_ERROR",
            )
            raise
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "AUTH_PROVIDER_UNAVAILABLE",
                provider="ad",
                actor=username,
                target=domain_hint,
                outcome="ldap_exception",
                error_code="INTERNAL_ERROR",
                message=str(exc),
            )
            raise AuthUnavailable("AD/LDAP provider unavailable") from exc

        log_event(
            logger,
            logging.INFO,
            "AUTH_PROVIDER_AD_BIND_SUCCESS",
            provider="ad",
            actor=username,
            target=domain_hint,
            outcome="success",
        )
        return user

    async def authenticate_for_source(self, *, source_id: int, username: str, password: str) -> UserInfo:
        if not settings.AD_ENABLED:
            raise AuthUnavailable("AD/LDAP authentication is disabled")

        if Connection is None or Server is None:
            raise AuthUnavailable("ldap3 is not installed in auth-service")

        if not username or not password:
            raise InvalidCredentials("Invalid credentials")

        log_event(
            logger,
            logging.INFO,
            "AUTH_LDAP_BIND_ATTEMPT",
            provider="ad",
            actor=username,
            source_id=int(source_id),
            outcome="attempt",
        )

        active_cfg = await _load_active_config_for_source(int(source_id))
        if not active_cfg:
            raise ProviderMisconfigured("No AD identity source configured")

        try:
            user = await self._authenticate_sync(active_cfg, username, password)
        except InvalidCredentials:
            log_event(
                logger,
                logging.WARNING,
                "AUTH_LDAP_BIND_FAILED",
                provider="ad",
                actor=username,
                source_id=int(source_id),
                outcome="invalid_credentials",
                error_code="UNAUTHENTICATED",
            )
            raise
        except ProviderMisconfigured:
            raise
        except SecretResolutionError:
            raise
        except AuthUnavailable:
            log_event(
                logger,
                logging.ERROR,
                "AUTH_PROVIDER_UNAVAILABLE",
                provider="ad",
                actor=username,
                source_id=int(source_id),
                outcome="unavailable",
                error_code="INTERNAL_ERROR",
            )
            raise
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "AUTH_LDAP_BIND_FAILED",
                provider="ad",
                actor=username,
                source_id=int(source_id),
                outcome="ldap_exception",
                error_code="INTERNAL_ERROR",
                message=str(exc),
            )
            raise AuthUnavailable("AD/LDAP provider unavailable") from exc

        log_event(
            logger,
            logging.INFO,
            "AUTH_LDAP_BIND_SUCCESS",
            provider="ad",
            actor=username,
            source_id=int(source_id),
            outcome="success",
        )
        return user

    async def change_password(
        self,
        username: str,
        current_password: str | None,
        new_password: str,
    ) -> None:
        raise NotImplementedError("Password change is handled by AD policies / self-service")


def _resolve_bind_password(src: dict, *, target: str | None) -> str:
    bind_password_ref = (src.get("bind_password_ref") or "").strip()
    if not bind_password_ref:
        return ""

    log_event(
        logger,
        logging.DEBUG,
        "AUTH_PROVIDER_AD_SECRET_RESOLVE_ATTEMPT",
        provider="ad",
        target=bind_password_ref,
        outcome="attempt",
    )
    try:
        bind_password = resolve_secret(bind_password_ref, default="")
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "AUTH_PROVIDER_AD_BIND_FAILED",
            provider="ad",
            target=target or bind_password_ref,
            outcome="secret_resolve_failed",
            error_code="INTERNAL_ERROR",
            message=str(exc),
        )
        raise SecretResolutionError("AD bind password secret unavailable") from exc

    log_event(
        logger,
        logging.DEBUG,
        "AUTH_PROVIDER_AD_SECRET_RESOLVE_SUCCESS",
        provider="ad",
        target=bind_password_ref,
        outcome="success",
    )
    return bind_password
