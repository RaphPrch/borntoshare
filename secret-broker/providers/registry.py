from __future__ import annotations

from typing import List, Optional

from core.errors import SecretInvalidRefError, SecretProviderFailureError
from core.settings import settings
from providers.env import EnvProvider
from providers.sm import SecretManagerProvider


def _split_csv(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _enforce_allowed_prefixes() -> list[str]:
    allowed = _split_csv(settings.allowed_prefixes)
    return allowed


def build_providers():
    allowed = _enforce_allowed_prefixes()
    providers = [SecretManagerProvider()]
    if "env://" in allowed and settings.allow_env_provider_dev:
        providers.append(EnvProvider())
    return providers


def resolve_secret(secret_ref: str) -> str:
    if not str(secret_ref or "").strip():
        raise SecretInvalidRefError(message="Missing ref", ref=secret_ref)

    for provider in build_providers():
        if provider.can_resolve(secret_ref):
            return provider.resolve(secret_ref)
    raise SecretProviderFailureError(message="No provider found for secret ref", ref=secret_ref)
