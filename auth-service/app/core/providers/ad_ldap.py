from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.providers.base import AuthProvider
from app.schemas.auth import UserInfo

settings = get_settings()
logger = get_logger(__name__)

try:
    # Optional dependency
    from ldap3 import Connection, Server, ALL, SUBTREE, Tls  # type: ignore
except Exception:  # pragma: no cover
    Connection = None  # type: ignore
    Server = None  # type: ignore
    ALL = None  # type: ignore
    SUBTREE = None  # type: ignore
    Tls = None  # type: ignore


def _cn_from_dn(dn: str) -> str:
    # DN like: CN=Group Name,OU=...,DC=...
    for part in dn.split(","):
        part = part.strip()
        if part.upper().startswith("CN="):
            return part[3:]
    return dn


@dataclass
class ADConfig:
    url: str
    base_dn: str
    user_filter: str
    groups_attr: str
    bind_user: str
    bind_password: str
    user_dn_template: str


class ADLDAPProvider(AuthProvider):
    """Authenticate a user against AD/LDAP.

    Supports two modes:
      1) Search + bind:
         - bind with AD_BIND_USER/AD_BIND_PASSWORD, search for user DN, then bind as user to verify password
      2) Direct bind:
         - if AD_USER_DN_TEMPLATE is set, format DN directly and bind as user

    Notes (DEV/V1):
      - No MFA here (handled later at IdP level).
      - Always prefer LDAPS in production.
    """

    name = "ad"

    def __init__(self) -> None:
        self.cfg = ADConfig(
            url=settings.AD_URL,
            base_dn=settings.AD_BASE_DN,
            user_filter=settings.AD_USER_FILTER,
            groups_attr=settings.AD_GROUPS_ATTRIBUTE,
            bind_user=settings.AD_BIND_USER,
            bind_password=settings.AD_BIND_PASSWORD,
            user_dn_template=settings.AD_USER_DN_TEMPLATE,
        )
        if not settings.AD_ENABLED:
            logger.warning("AD provider instantiated but AD_ENABLED is false")

    async def authenticate(self, username: str, password: str) -> UserInfo:
        if not settings.AD_ENABLED:
            raise ValueError("AD/LDAP authentication is disabled (AD_ENABLED=false)")

        if Connection is None or Server is None:
            raise RuntimeError("ldap3 is not installed. Add 'ldap3' to requirements to enable AD auth.")

        if not username or not password:
            raise ValueError("Invalid credentials")

        server = Server(self.cfg.url, get_info=ALL)

        # ----------------------------
        # Mode 2: direct bind via template
        # ----------------------------
        if self.cfg.user_dn_template:
            user_dn = self.cfg.user_dn_template.format(username=username)
            if not Connection(server, user=user_dn, password=password, auto_bind=True):
                raise ValueError("Invalid credentials")

            # Optional: fetch attributes via a service bind if available
            display_name = None
            email = None
            roles: List[str] = []
            if self.cfg.bind_user and self.cfg.bind_password:
                with Connection(server, user=self.cfg.bind_user, password=self.cfg.bind_password, auto_bind=True) as c:
                    flt = self.cfg.user_filter.format(username=username)
                    attrs = ["displayName", "mail", self.cfg.groups_attr]
                    ok = c.search(self.cfg.base_dn, flt, search_scope=SUBTREE, attributes=attrs, size_limit=1)
                    if ok and c.entries:
                        e = c.entries[0]
                        display_name = str(getattr(e, "displayName", "") or "") or None
                        email = str(getattr(e, "mail", "") or "") or None
                        try:
                            groups = list(getattr(e, self.cfg.groups_attr).values)  # type: ignore
                        except Exception:
                            groups = []
                        roles = [_cn_from_dn(g) for g in groups]

            return UserInfo(
                user_id=username,
                username=username,
                display_name=display_name,
                email=email,
                roles=roles,
                permissions=[],
                auth_source="ad",
            )

        # ----------------------------
        # Mode 1: search DN using bind account, then bind as user
        # ----------------------------
        if not (self.cfg.bind_user and self.cfg.bind_password):
            raise RuntimeError(
                "AD_BIND_USER/AD_BIND_PASSWORD must be configured when AD_USER_DN_TEMPLATE is empty."
            )

        with Connection(server, user=self.cfg.bind_user, password=self.cfg.bind_password, auto_bind=True) as search_conn:
            flt = self.cfg.user_filter.format(username=username)
            attrs = ["distinguishedName", "displayName", "mail", self.cfg.groups_attr]
            ok = search_conn.search(
                search_base=self.cfg.base_dn,
                search_filter=flt,
                search_scope=SUBTREE,
                attributes=attrs,
                size_limit=1,
            )
            if not ok or not search_conn.entries:
                logger.warning("AD user not found | username=%s | filter=%s", username, flt)
                raise ValueError("Invalid credentials")

            entry = search_conn.entries[0]
            user_dn = str(getattr(entry, "distinguishedName").value)  # type: ignore

            # Bind as the user to validate password
            try:
                with Connection(server, user=user_dn, password=password, auto_bind=True):
                    pass
            except Exception:
                raise ValueError("Invalid credentials")

            display_name = str(getattr(entry, "displayName", "") or "") or None
            email = str(getattr(entry, "mail", "") or "") or None

            try:
                groups = list(getattr(entry, self.cfg.groups_attr).values)  # type: ignore
            except Exception:
                groups = []
            roles = [_cn_from_dn(g) for g in groups]

            return UserInfo(
                user_id=username,
                username=username,
                display_name=display_name,
                email=email,
                roles=roles,
                permissions=[],
                auth_source="ad",
            )

    async def change_password(self, username: str, current_password: str, new_password: str) -> None:
        raise NotImplementedError("Password change is handled by AD policies / self-service")
