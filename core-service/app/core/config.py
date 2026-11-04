from __future__ import annotations

import urllib.parse
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    core-service settings, read from the environment (podman-compose.yml passes the .env values).

    A required variable that is missing stops the service at startup instead of falling back to a default.
    """

    model_config = SettingsConfigDict(extra="ignore")

    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "core-service"
    API_PREFIX: str = "/api"
    APP_VERSION: str = "0.1.0"

    # One token shared by every service (X-Internal-Token)
    INTERNAL_TOKEN: str = Field(min_length=1)

    # Database (MariaDB)
    DB_DRIVER: str = "mariadb+pymysql"
    DB_HOST: str = Field(min_length=1)
    DB_PORT: int = 3306
    DB_NAME: str = Field(min_length=1)
    DB_USER: str = Field(min_length=1)
    DB_PASSWORD: str = Field(min_length=1)
    # Full connection string chosen in Advanced Settings › Infrastructure (runtime file), replaces DB_*
    DATABASE_URL_OVERRIDE: str | None = None
    # Where the running connection comes from: "env" (.env) or "runtime" (Infrastructure page)
    DB_CONFIG_SOURCE: str = "env"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800
    DB_SCHEMA_GUARD_ENABLED: bool = True

    # Audit database (borntoshare_logging): same server and account as the main database unless set
    LOGGING_DATABASE_URL: str | None = None
    LOGGING_DB_NAME: str = "borntoshare_logging"
    LOGGING_DB_HOST: str | None = None
    LOGGING_DB_PORT: int | None = None
    LOGGING_DB_USER: str | None = None
    LOGGING_DB_PASSWORD: str | None = None

    # Dramatiq broker (Redis) and the watchdog that republishes jobs stuck in QUEUED
    CAPSULE_BROKER_URL: str = Field(min_length=1)
    JOB_WATCHDOG_ENABLED: bool = True
    JOB_WATCHDOG_INTERVAL_SECONDS: int = Field(default=30, ge=15)
    JOB_WATCHDOG_QUEUED_TIMEOUT_SECONDS: int = Field(default=300, ge=30)
    JOB_WATCHDOG_MAX_REPUBLISH: int = Field(default=1, ge=0)
    JOB_WATCHDOG_LIMIT: int = Field(default=200, ge=1, le=1000)

    @field_validator("LOG_LEVEL")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = str(value or "INFO").strip().upper()
        aliases = {"WARN": "WARNING", "ERR": "ERROR", "TRACE": "DEBUG"}
        resolved = aliases.get(normalized, normalized)
        if resolved not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("Invalid LOG_LEVEL")
        return resolved

    @model_validator(mode="after")
    def _logging_database_defaults(self) -> "Settings":
        self.LOGGING_DB_HOST = self.LOGGING_DB_HOST or self.DB_HOST
        self.LOGGING_DB_PORT = self.LOGGING_DB_PORT or self.DB_PORT
        self.LOGGING_DB_USER = self.LOGGING_DB_USER or self.DB_USER
        self.LOGGING_DB_PASSWORD = self.LOGGING_DB_PASSWORD or self.DB_PASSWORD
        return self

    # =================================================
    # Helpers
    # =================================================
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
            f"{self.DB_DRIVER}://{user}:{pwd}"
            f"@{self.LOGGING_DB_HOST}:{self.LOGGING_DB_PORT}/{self.LOGGING_DB_NAME}"
        )

    def fastapi_kwargs(self) -> dict:
        # No interactive API documentation: the API is internal, behind the BFF
        kwargs = {
            "title": self.SERVICE_NAME,
            "version": self.APP_VERSION,
            "docs_url": None,
            "redoc_url": None,
            "openapi_url": None,
        }
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
    return _apply_runtime_database(Settings())
