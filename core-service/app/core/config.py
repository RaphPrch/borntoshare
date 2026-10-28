from __future__ import annotations

import os
import urllib.parse
from functools import lru_cache
from pydantic import BaseModel, Field, field_validator


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    """
    core-service settings (BornToShare)

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
    # Full connection string chosen in Advanced Settings › Infrastructure (runtime file), replaces DB_*
    DATABASE_URL_OVERRIDE: str | None = Field(default=None)
    # Where the running connection comes from: "env" (.env) or "runtime" (Infrastructure page)
    DB_CONFIG_SOURCE: str = Field(default="env")

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
    SERVICE_NAME: str = Field(default=os.getenv("SERVICE_NAME", "core-service"))
    API_PREFIX: str = Field(default=os.getenv("API_PREFIX", "/api"))
    # Opens the non-/internal/ orchestration routes (/governance/*) to the frontend BFF without a token.
    ALLOW_PUBLIC_API: bool = Field(default=_env_flag("B2S_ALLOW_PUBLIC_API", "false"))
    ENABLE_DOCS: bool = Field(default=os.getenv("ENABLE_DOCS", "true").lower() == "true")

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

    # =================================================
    # 🧵 Provisioning jobs (Dramatiq broker + watchdog)
    # =================================================
    CAPSULE_BROKER_URL: str = Field(default=os.getenv("CAPSULE_BROKER_URL", "").strip())
    # Republishes jobs stuck in QUEUED for longer than the timeout.
    JOB_WATCHDOG_ENABLED: bool = Field(default=_env_flag("JOB_WATCHDOG_ENABLED", "1"))
    JOB_WATCHDOG_INTERVAL_SECONDS: int = Field(default=max(15, int(os.getenv("JOB_WATCHDOG_INTERVAL_SECONDS", "30"))))
    JOB_WATCHDOG_QUEUED_TIMEOUT_SECONDS: int = Field(
        default=max(30, int(os.getenv("JOB_WATCHDOG_QUEUED_TIMEOUT_SECONDS", "300")))
    )
    JOB_WATCHDOG_MAX_REPUBLISH: int = Field(default=max(0, int(os.getenv("JOB_WATCHDOG_MAX_REPUBLISH", "1"))))
    JOB_WATCHDOG_LIMIT: int = Field(default=max(1, min(int(os.getenv("JOB_WATCHDOG_LIMIT", "200")), 1000)))

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

    @field_validator("INTERNAL_TOKEN_TTL_SEC")
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
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
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


def _apply_runtime_database(settings: Settings) -> Settings:
    """The database chosen on the Infrastructure page wins over .env (applied at startup)."""
    from app.core.runtime_config import parse_dsn, read_database_config

    config = read_database_config()
    if not config:
        return settings
    updates: dict = {"DB_CONFIG_SOURCE": "runtime"}
    if config["mode"] == "dsn" and str(config.get("dsn") or "").strip():
        dsn = str(config["dsn"]).strip()
        parts = parse_dsn(dsn)
        updates.update(
            DATABASE_URL_OVERRIDE=dsn,
            DB_HOST=parts["host"],
            DB_PORT=int(parts["port"]),
            DB_NAME=parts["name"] or settings.DB_NAME,
            DB_USER=parts["user"] or settings.DB_USER,
        )
        if str(config.get("logging_dsn") or "").strip():
            updates["LOGGING_DATABASE_URL"] = str(config["logging_dsn"]).strip()
    elif config["mode"] == "fields":
        updates.update(
            DB_HOST=str(config.get("host") or settings.DB_HOST),
            DB_PORT=int(config.get("port") or settings.DB_PORT),
            DB_NAME=str(config.get("name") or settings.DB_NAME),
            DB_USER=str(config.get("user") or settings.DB_USER),
            DB_PASSWORD=str(config.get("password") or settings.DB_PASSWORD),
            # The logging database lives on the same server
            LOGGING_DB_HOST=str(config.get("host") or settings.LOGGING_DB_HOST),
            LOGGING_DB_PORT=int(config.get("port") or settings.LOGGING_DB_PORT),
            LOGGING_DB_USER=str(config.get("user") or settings.LOGGING_DB_USER),
            LOGGING_DB_PASSWORD=str(config.get("password") or settings.LOGGING_DB_PASSWORD),
            LOGGING_DB_NAME=str(config.get("logging_name") or settings.LOGGING_DB_NAME),
        )
    return settings.model_copy(update=updates)


@lru_cache
def get_settings() -> Settings:
    settings = _apply_runtime_database(Settings())

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
