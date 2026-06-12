from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # =================================================
    # 🧩 Application
    # =================================================
    APP_ENV: str = "dev"  # dev | staging | prod
    VERSION: str = "2026.01-v1"

    # =================================================
    # 📝 Logging
    # =================================================
    LOG_LEVEL: str = "INFO"

    # =================================================
    # 🌍 CORS (credentials-friendly)
    # =================================================
    CORS_ALLOW_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8081",
        "http://borntoshare.local",
    ]

    # =================================================
    # 🍪 Cookies / Sessions
    # =================================================
    SESSION_COOKIE_NAME: str = "b2s_session"
    COOKIE_SAMESITE: str = "lax"  # lax | strict | none
    COOKIE_DOMAIN: Optional[str] = None

    PRINCIPAL_COOKIE_NAME: str = "b2s_principal"
    PRINCIPAL_TTL_SECONDS: int = 15 * 60
    PRINCIPAL_SIGNING_KEY: str = "dev_principal_signing_key_change_me"
    PRINCIPAL_COOKIE_SAMESITE: str = "lax"  # lax | strict | none
    PRINCIPAL_COOKIE_SECURE: bool = False

    SESSION_TTL_SECONDS: int = 8 * 60 * 60       # 8h hard TTL
    SESSION_IDLE_TIMEOUT: int = 30 * 60          # 30 min inactivity
    SESSION_STORE_BACKEND: str = "memory"        # memory | redis

    # Redis session backend (V1)
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_USERNAME: Optional[str] = None
    REDIS_PASSWORD: Optional[str] = None
    REDIS_TLS: bool = False
    REDIS_KEY_PREFIX: str = "bts:auth"
    REDIS_TIMEOUT_SECONDS: float = 2.0

    # =================================================
    # 🔐 Providers & Feature flags
    # =================================================
    ENABLED_PROVIDERS: List[str] = ["ad", "local"]
    DEFAULT_AUTH_PROVIDER: str = "ad"

    # =================================================
    # 🧠 Local provider (DAL)
    # =================================================
    DAL_URL: str = "http://dal-service:8000"
    DAL_VALIDATE_CREDENTIALS_PATH: str = "/internal/auth/local/verify"
    DAL_CHANGE_PASSWORD_PATH: str = "/internal/auth/change-password"
    DAL_TIMEOUT_SECONDS: int = 5

    # =================================================
    # 🟩 Active Directory / LDAP
    # =================================================
    AD_ENABLED: bool = False
    AD_USER_FILTER: str = "(sAMAccountName={username})"
    AD_USER_DN_TEMPLATE: str = ""
    AD_CONNECT_TIMEOUT_SECONDS: int = 5
    ALLOW_INSECURE_LDAP: bool = False

    # =================================================
    # 🔐 Internal service-to-service authentication (V1)
    # =================================================
    # V1: static shared token only
    INTERNAL_TOKEN: str
    SERVICE_TOKEN: Optional[str] = None
    INTERNAL_SERVICE_NAME: str = "auth"
    INTERNAL_SERVICE_SCOPE: str = "jobs:read"

    # =================================================
    # 🔐 Secret broker (V1)
    # =================================================
    B2S_SECRET_BROKER_URL: str = "http://secret-broker:8010"
    B2S_SECRET_BROKER_TIMEOUT_SECONDS: float = 5.0
    B2S_SECRET_WRITE_TOKEN: Optional[str] = None
    DEFAULT_AD_BIND_PASSWORD_REF: Optional[str] = None

    # =================================================
    # ⚙️ Pydantic config
    # =================================================
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("LOG_LEVEL")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = str(value or "INFO").strip().upper()
        aliases = {"WARN": "WARNING", "ERR": "ERROR", "TRACE": "DEBUG"}
        resolved = aliases.get(normalized, normalized)
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        if resolved not in allowed:
            raise ValueError("Invalid LOG_LEVEL value")
        return resolved

    @field_validator("COOKIE_SAMESITE", "PRINCIPAL_COOKIE_SAMESITE")
    @classmethod
    def _validate_samesite(cls, value: str) -> str:
        normalized = str(value or "lax").strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("Invalid SameSite value")
        return normalized

    @field_validator("ENABLED_PROVIDERS", mode="before")
    @classmethod
    def _normalize_enabled_providers(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return ["ad", "local"]
        normalized: list[str] = []
        for item in value:
            key = str(item or "").strip().lower()
            if key and key not in normalized:
                normalized.append(key)
        return normalized or ["local"]

    @field_validator(
        "DAL_TIMEOUT_SECONDS",
        "AD_CONNECT_TIMEOUT_SECONDS",
        "B2S_SECRET_BROKER_TIMEOUT_SECONDS",
        "REDIS_TIMEOUT_SECONDS",
    )
    @classmethod
    def _validate_positive_timeout(cls, value: float | int) -> float | int:
        if float(value) <= 0:
            raise ValueError("Timeout must be > 0")
        return value

    @field_validator("SESSION_STORE_BACKEND")
    @classmethod
    def _validate_session_store_backend(cls, value: str) -> str:
        normalized = str(value or "memory").strip().lower()
        if normalized not in {"memory", "redis"}:
            raise ValueError("SESSION_STORE_BACKEND must be one of: memory, redis")
        return normalized

    @field_validator("SESSION_TTL_SECONDS", "SESSION_IDLE_TIMEOUT", "PRINCIPAL_TTL_SECONDS")
    @classmethod
    def _validate_positive_ttl(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("TTL must be > 0")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()

    # -------------------------------------------------
    # 🔥 Safety checks (V1)
    # -------------------------------------------------

    # ---- Internal auth (mandatory)
    if not settings.INTERNAL_TOKEN:
        raise RuntimeError(
            "Misconfiguration: INTERNAL_TOKEN is required (V1 static mode)"
        )

    # ---- Provider sanity
    default_provider = (settings.DEFAULT_AUTH_PROVIDER or "").strip().lower()
    if default_provider and default_provider not in settings.ENABLED_PROVIDERS:
        raise RuntimeError(
            "DEFAULT_AUTH_PROVIDER must be listed in ENABLED_PROVIDERS"
        )

    return settings
