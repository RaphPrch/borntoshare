from __future__ import annotations

import os
import urllib.parse
from functools import lru_cache
from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    """
    DAL-Service settings (BornToShare)

    Goals:
    - DEV simple (HTTP, no strict policies)
    - Consistent internal service-to-service auth
    - Single DB URL for SQLAlchemy
    """

    # =================================================
    # 🧩 Core
    # =================================================
    APP_ENV: str = Field(default=os.getenv("APP_ENV", "dev"))
    LOG_LEVEL: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))

    # =================================================
    # 🗄️ Database (MariaDB)
    # =================================================
    DB_DRIVER: str = Field(default=os.getenv("DB_DRIVER", "mariadb+pymysql"))
    DB_HOST: str = Field(default=os.getenv("DB_HOST", "192.168.100.12"))
    DB_PORT: int = Field(default=int(os.getenv("DB_PORT", "3306")))
    DB_NAME: str = Field(default=os.getenv("DB_NAME", "b2s"))
    DB_USER: str = Field(default=os.getenv("DB_USER", "b2s"))
    DB_PASSWORD: str = Field(default=os.getenv("DB_PASSWORD", "b2s"))

    # =================================================
    # 🗄️ Logging Database (MariaDB) — borntoshare_logging
    # =================================================
    # Prefer explicit URL if provided. Otherwise build from LOGGING_DB_* parts.
    LOGGING_DATABASE_URL: str | None = Field(default=os.getenv("LOGGING_DATABASE_URL"))
    LOGGING_DB_DRIVER: str = Field(default=os.getenv("LOGGING_DB_DRIVER", "mariadb+pymysql"))
    LOGGING_DB_HOST: str = Field(default=os.getenv("LOGGING_DB_HOST", "db_logging"))
    LOGGING_DB_PORT: int = Field(default=int(os.getenv("LOGGING_DB_PORT", "3306")))
    LOGGING_DB_NAME: str = Field(default=os.getenv("LOGGING_DB_NAME", "borntoshare_logging"))
    LOGGING_DB_USER: str = Field(default=os.getenv("LOGGING_DB_USER", "b2s"))
    LOGGING_DB_PASSWORD: str = Field(default=os.getenv("LOGGING_DB_PASSWORD", "b2s"))

    DB_POOL_SIZE: int = Field(default=int(os.getenv("DB_POOL_SIZE", "10")))
    DB_MAX_OVERFLOW: int = Field(default=int(os.getenv("DB_MAX_OVERFLOW", "20")))
    DB_POOL_RECYCLE: int = Field(default=int(os.getenv("DB_POOL_RECYCLE", "1800")))
    DB_SCHEMA_GUARD_ENABLED: bool = Field(
        default=os.getenv("DB_SCHEMA_GUARD_ENABLED", "true").lower() == "true"
    )

    # =================================================
    # 🌐 API
    # =================================================
    SERVICE_NAME: str = Field(default=os.getenv("SERVICE_NAME", "dal-service"))
    API_PREFIX: str = Field(default=os.getenv("API_PREFIX", ""))
    ENABLE_DOCS: bool = Field(default=os.getenv("ENABLE_DOCS", "true").lower() == "true")

    # =================================================
    # 🧾 Activity bridge (DAL -> wizard logging DB)
    # =================================================
    WIZARD_RUNTIME_BASE: str = Field(default=os.getenv("WIZARD_RUNTIME_BASE", "http://wizard-ui:8080/api/runtime"))
    WIZARD_ACTIVITY_TIMEOUT_SECONDS: int = Field(default=int(os.getenv("WIZARD_ACTIVITY_TIMEOUT_SECONDS", "5")))
    GOVERNANCE_URL: str = Field(default=os.getenv("GOVERNANCE_URL", "http://governance-service:8000"))

    # =================================================
    # 🔐 Internal service-to-service authentication
    # =================================================
    # static | hmac
    INTERNAL_TOKEN_MODE: str = Field(
        default=os.getenv("INTERNAL_TOKEN_MODE", "hmac").lower()
    )

    # ⚠️ MUST be unset when mode=hmac
    INTERNAL_TOKEN: str | None = Field(
        default=os.getenv("INTERNAL_TOKEN")
    )

    # Format: "kid1:secret1,kid2:secret2"
    INTERNAL_TOKEN_KEYS: str = Field(
        default=os.getenv("INTERNAL_TOKEN_KEYS", "")
    )

    INTERNAL_TOKEN_TTL_SEC: int = Field(
        default=int(os.getenv("INTERNAL_TOKEN_TTL_SEC", "300"))
    )

    @field_validator("LOG_LEVEL")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = str(value or "INFO").strip().upper()
        aliases = {"WARN": "WARNING", "ERR": "ERROR", "TRACE": "DEBUG"}
        resolved = aliases.get(normalized, normalized)
        if resolved not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("Invalid LOG_LEVEL")
        return resolved

    @field_validator("INTERNAL_TOKEN_MODE")
    @classmethod
    def _validate_internal_token_mode(cls, value: str) -> str:
        normalized = str(value or "hmac").strip().lower()
        if normalized not in {"hmac", "static"}:
            raise ValueError("INTERNAL_TOKEN_MODE must be 'hmac' or 'static'")
        return normalized

    @field_validator("WIZARD_ACTIVITY_TIMEOUT_SECONDS", "INTERNAL_TOKEN_TTL_SEC")
    @classmethod
    def _validate_positive_ints(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("Value must be > 0")
        return int(value)

    # =================================================
    # Helpers
    # =================================================
    @property
    def is_prod(self) -> bool:
        return self.APP_ENV.lower() in {"prod", "production"}

    @property
    def sqlalchemy_url(self) -> str:
        user = urllib.parse.quote_plus(self.DB_USER)
        pwd = urllib.parse.quote_plus(self.DB_PASSWORD)
        return (
            f"{self.DB_DRIVER}://{user}:{pwd}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


    @property
    def logging_sqlalchemy_url(self) -> str:
        if self.LOGGING_DATABASE_URL:
            return str(self.LOGGING_DATABASE_URL).strip()
        user = urllib.parse.quote_plus(self.LOGGING_DB_USER)
        pwd = urllib.parse.quote_plus(self.LOGGING_DB_PASSWORD)
        return (
            f"{self.LOGGING_DB_DRIVER}://{user}:{pwd}"
            f"@{self.LOGGING_DB_HOST}:{self.LOGGING_DB_PORT}/{self.LOGGING_DB_NAME}"
        )

    def fastapi_kwargs(self) -> dict:
        kwargs = {
            "title": self.SERVICE_NAME,
            "version": os.getenv("APP_VERSION", "0.1.0"),
        }
        if self.ENABLE_DOCS and not self.is_prod:
            kwargs.update(
                {
                    "docs_url": "/docs",
                    "redoc_url": "/redoc",
                    "openapi_url": "/openapi.json",
                }
            )
        else:
            kwargs.update(
                {"docs_url": None, "redoc_url": None, "openapi_url": None}
            )
        return kwargs


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # -------------------------------------------------
    # 🔥 Safety checks (CRITICAL)
    # -------------------------------------------------
    if settings.INTERNAL_TOKEN_MODE == "hmac" and settings.INTERNAL_TOKEN:
        raise RuntimeError(
            "Misconfiguration: INTERNAL_TOKEN must not be set when INTERNAL_TOKEN_MODE=hmac"
        )

    # NOTE:
    # We intentionally avoid raising at import time when hmac keyring is absent,
    # because many unit tests import modules that read settings eagerly.
    # Runtime guards in request-time auth paths still enforce token validity.

    if settings.INTERNAL_TOKEN_MODE == "static" and not (settings.INTERNAL_TOKEN or "").strip():
        raise RuntimeError(
            "Misconfiguration: INTERNAL_TOKEN is required when INTERNAL_TOKEN_MODE=static"
        )

    return settings
