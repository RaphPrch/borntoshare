from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

def _split_csv(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]

@dataclass(frozen=True)
class Settings:
    env: str = (os.getenv("APP_ENV") or os.getenv("B2S_ENV") or os.getenv("ENV") or "dev").strip().lower()

    # V1: static internal token only
    internal_token: Optional[str] = os.getenv("INTERNAL_TOKEN")

    # V1: allowed ref prefixes
    allowed_prefixes: str = os.getenv(
        "B2S_SECRET_ALLOWED_PREFIXES",
        "sm://",
    ).strip()

    # Dev-only explicit opt-in for env:// provider
    allow_env_provider_dev: bool = os.getenv("B2S_SECRET_ALLOW_ENV_PROVIDER", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    # Persistent secrets directory (V1)
    secrets_dir: str = os.getenv("B2S_SECRETS_DIR", "/data/secrets").strip()

    # Filesystem is the default and only supported persistence provider in V1.
    secret_provider: str = os.getenv("B2S_SECRET_PROVIDER", "filesystem").strip().lower()

    # Dev-only: allow in-memory secrets set via API
    allow_write: bool = os.getenv("B2S_SECRET_ALLOW_WRITE", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    # Optional protection for dev writes
    write_token: Optional[str] = os.getenv("B2S_SECRET_WRITE_TOKEN")

    # TTL for in-memory values (DEV only)
    secret_mem_ttl_sec: int = int(os.getenv("B2S_SECRET_MEM_TTL_SEC", "60"))

settings = Settings()

def _validate_settings() -> None:
    allowed = _split_csv(settings.allowed_prefixes)
    if settings.secret_provider != "filesystem":
        raise RuntimeError("Unsupported B2S_SECRET_PROVIDER, expected 'filesystem'")

    if not allowed:
        raise RuntimeError("B2S_SECRET_ALLOWED_PREFIXES must not be empty")

    supported = {"sm://", "env://"}
    unknown = [p for p in allowed if p not in supported]
    if unknown:
        raise RuntimeError(f"Unsupported prefixes in B2S_SECRET_ALLOWED_PREFIXES: {','.join(unknown)}")

    if settings.env == "prod":
        if allowed != ["sm://"]:
            raise RuntimeError("In prod, only sm:// is allowed for secrets")
        if settings.allow_env_provider_dev:
            raise RuntimeError("B2S_SECRET_ALLOW_ENV_PROVIDER is forbidden in prod")

    if "env://" in allowed and not settings.allow_env_provider_dev:
        raise RuntimeError("env:// requires B2S_SECRET_ALLOW_ENV_PROVIDER=true in non-prod")

_validate_settings()
