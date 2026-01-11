from __future__ import annotations

from typing import Dict, List

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.providers.base import AuthProvider
from app.core.providers.keycloak import KeycloakProvider
from app.core.providers.local_dal import DalLocalProvider
from app.core.providers.dev import DevProvider
from app.core.providers.ad_ldap import ADLDAPProvider

settings = get_settings()
logger = get_logger("providers-registry")


def build_registry() -> Dict[str, AuthProvider]:
    """Build provider registry.

    The auth-service can expose several authentication providers:
      - local: local users stored in DAL (bootstrap / break-glass)
      - ad: AD/LDAP direct bind (optional, disabled by default)
      - keycloak: OIDC broker / IdP (optional)
      - dev: dev-only provider (optional)
    """
    reg: Dict[str, AuthProvider] = {}

    # Local provider is always available
    reg["local"] = DalLocalProvider()

    # AD/LDAP (only if enabled)
    if getattr(settings, "AD_ENABLED", False):
        reg["ad"] = ADLDAPProvider()

    # IdP (Keycloak) (only if enabled)
    if getattr(settings, "KEYCLOAK_ENABLED", False):
        reg["keycloak"] = KeycloakProvider()

    # Dev provider
    if getattr(settings, "ENABLE_DEV_PROVIDER", False):
        reg["dev"] = DevProvider()

    return reg


def ordered_providers(registry: Dict[str, AuthProvider]) -> List[AuthProvider]:
    ordered: List[AuthProvider] = []
    for name in settings.ENABLED_PROVIDERS:
        key = (name or "").lower()
        if key in registry:
            ordered.append(registry[key])
    return ordered


def choose_provider(name: str) -> AuthProvider:
    registry = build_registry()
    key = (name or settings.DEFAULT_AUTH_PROVIDER or "local").lower()
    if key not in registry:
        raise ValueError(f"Unknown or disabled auth provider '{name}'")
    return registry[key]
