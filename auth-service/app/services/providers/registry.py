from __future__ import annotations

from typing import Dict, List

from app.core.logging import get_logger
from app.services.providers.base import AuthProvider
from app.services.providers.local_core import CoreLocalProvider
from app.services.providers.ad_ldap import ADLDAPProvider

# The directories with sign-in enabled are chosen in the application; local accounts always work
AUTH_PROVIDERS = ("ad", "local")
DEFAULT_AUTH_PROVIDER = "ad"
logger = get_logger("providers-registry")


def build_registry() -> Dict[str, AuthProvider]:
    """Build provider registry.

    Providers:
      - local: local users stored in core-service
      - ad: AD/LDAP direct bind (optional, disabled by default)
    """
    reg: Dict[str, AuthProvider] = {}

    # Local provider is always available
    reg["local"] = CoreLocalProvider()

    # AD/LDAP: used for the directories with sign-in enabled
    reg["ad"] = ADLDAPProvider()

    return reg


def ordered_providers(registry: Dict[str, AuthProvider]) -> List[AuthProvider]:
    ordered: List[AuthProvider] = []
    for name in AUTH_PROVIDERS:
        key = (name or "").lower()
        if key in registry:
            ordered.append(registry[key])
    return ordered


def choose_provider(name: str) -> AuthProvider:
    registry = build_registry()
    key = (name or DEFAULT_AUTH_PROVIDER).lower()
    if key not in registry:
        raise ValueError(f"Unknown or disabled auth provider '{name}'")
    return registry[key]
