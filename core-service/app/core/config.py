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
    # The names default to those of the wizard: .env needs DB_HOST only; the password is a secret (DB_PASSWORD_FILE)
    DB_HOST: str = Field(min_length=1)
    DB_PORT: int = 3306
    DB_NAME: str = "borntoshare"
    DB_USER: str = "b2s_core"
    DB_PASSWORD: str = Field(min_length=1)
    # Shown on the Infrastructure page: the account of the schema changes (make deploy), never used by this service
    DB_MIGRATE_USER: str = "b2s_migrate"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800
    DB_SCHEMA_GUARD_ENABLED: bool = True

    # Audit database (borntoshare_logging): same server and account as the main database unless set
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
        user = urllib.parse.quote_plus(self.DB_USER)
        pwd = urllib.parse.quote_plus(self.DB_PASSWORD)
        return (
            f"{self.DB_DRIVER}://{user}:{pwd}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


    @property
    def logging_sqlalchemy_url(self) -> str:
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
