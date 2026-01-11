from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # =================================================
    # 🧩 Application
    # =================================================
    APP_NAME: str = "borntoshare-auth-service"
    APP_ENV: str = "dev"
    VERSION: str = "2025.12-modern-v3.1"

    # =================================================
    # 📝 Logging
    # =================================================
    LOG_LEVEL: str = "INFO"          # ERROR | WARNING | INFO | DEBUG
    B2S_DEBUG: bool = False
    B2S_LOG_LEVEL: Optional[str] = None

    # =================================================
    # 🌍 CORS (credentials-friendly)
    # =================================================
    # ⚠️ DOIT matcher le frontend + gateway
    CORS_ALLOW_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8081",
        "http://gateway-service:8000",
        "http://borntoshare.local",
    ]

    # =================================================
    # 🍪 Cookies / Sessions
    # =================================================
    SECRET_KEY: str = "dev_secret_change_me"

    SESSION_COOKIE_NAME: str = "b2s_session"

    # DEV = False (HTTP) | PROD = True (HTTPS)
    COOKIE_SECURE: bool = False

    # lax = recommandé (login + redirect OK)
    COOKIE_SAMESITE: str = "lax"

    # Généralement None → cookie scope = host courant
    COOKIE_DOMAIN: Optional[str] = None

    # TTL absolu (8h)
    SESSION_TTL_SECONDS: int = 8 * 60 * 60

    # Idle timeout (30 min)
    SESSION_IDLE_TIMEOUT: int = 30 * 60

    # =================================================
    # 🗄️ Session Store
    # =================================================
    # inmemory = DEV
    # redis = PROD / HA
    SESSION_STORE: str = "inmemory"
    REDIS_URL: str = "redis://redis:6379/0"

    # =================================================
    # 🔐 Providers & Feature flags
    # =================================================
    # ⚠️ L’ordre compte (fallback)
    ENABLED_PROVIDERS: List[str] = ["local", "keycloak"]

    ENABLE_DEV_PROVIDER: bool = True
    ENABLE_CHANGE_PASSWORD: bool = True

    # Provider par défaut si payload.provider est absent
    DEFAULT_AUTH_PROVIDER: str = "local"

    # =================================================
    # 🧠 Local provider (DAL)
    # =================================================
    DAL_URL: str = "http://dal-service:8000"

    # V2 – sans fuite de hash
    DAL_VALIDATE_CREDENTIALS_PATH: str = "/internal/auth/local/verify"
    DAL_CHANGE_PASSWORD_PATH: str = "/internal/auth/change-password"

    DAL_TIMEOUT_SECONDS: int = 5

    # =================================================
    # 🚨 Emergency admin (DEV / break-glass)
    # =================================================
    EMERGENCY_ADMIN_ENABLED: bool = False
    EMERGENCY_ADMIN_USERNAME: str = "admin"
    EMERGENCY_ADMIN_PASSWORD_HASH: str = ""

    # =================================================
    # 🟦 Keycloak
    # =================================================
    KEYCLOAK_ENABLED: bool = False

    KEYCLOAK_URL: str = ""
    KEYCLOAK_REALM: str = ""
    KEYCLOAK_CLIENT_ID: str = ""
    KEYCLOAK_CLIENT_SECRET: str = ""

    # ⚠️ DOIT matcher le frontend
    KEYCLOAK_REDIRECT_URI: str = "http://borntoshare.local/login/callback"

    KEYCLOAK_SCOPES: str = "openid profile email"
    KEYCLOAK_PKCE_ENABLED: bool = True
    KEYCLOAK_PASSWORD_GRANT_ENABLED: bool = False

    # DEV = False | PROD = True
    KEYCLOAK_VALIDATE_JWT: bool = False

    # =================================================
    # 🏢 Active Directory / LDAP
    # =================================================
    AD_ENABLED: bool = False
    AD_URL: str = "ldap://ad.example.local:389"
    AD_BASE_DN: str = "DC=example,DC=local"
    AD_USER_DN_TEMPLATE: str = ""
    AD_BIND_USER: str = ""
    AD_BIND_PASSWORD: str = ""
    AD_USER_FILTER: str = "(&(objectClass=user)(sAMAccountName={username}))"
    AD_GROUPS_ATTRIBUTE: str = "memberOf"

    # =================================================
    # ⚙️ Pydantic config
    # =================================================
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()

    # -------------------------------------------------
    # 🔥 Safety checks
    # -------------------------------------------------
    if settings.APP_ENV != "dev" and settings.SECRET_KEY.startswith("dev_"):
        raise RuntimeError(
            "Insecure SECRET_KEY detected in non-dev environment"
        )

    if settings.COOKIE_SECURE and settings.APP_ENV == "dev":
        raise RuntimeError(
            "COOKIE_SECURE=true is incompatible with HTTP (dev environment)"
        )

    return settings
