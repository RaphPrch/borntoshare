from __future__ import annotations
from typing import List
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.providers.base import AuthProvider
from app.schemas.auth import UserInfo

settings = get_settings()
logger = get_logger(__name__)

class KeycloakProvider(AuthProvider):
    name = "keycloak"

    def base(self) -> str:
        return settings.KEYCLOAK_URL.rstrip("/") + f"/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect"

    async def authenticate(self, username: str, password: str) -> UserInfo:
        if not settings.KEYCLOAK_ENABLED:
            raise ValueError("Keycloak provider disabled")
        if not settings.KEYCLOAK_PASSWORD_GRANT_ENABLED:
            raise ValueError("Password grant disabled (use /auth/keycloak/login redirect flow)")

        token_url = self.base() + "/token"
        payload = {
            "grant_type": "password",
            "client_id": settings.KEYCLOAK_CLIENT_ID,
            "username": username,
            "password": password,
            "scope": settings.KEYCLOAK_SCOPES,
        }
        if settings.KEYCLOAK_CLIENT_SECRET:
            payload["client_secret"] = settings.KEYCLOAK_CLIENT_SECRET

        logger.info("Keycloak password-grant | username=%s", username)
        async with httpx.AsyncClient(verify=settings.KEYCLOAK_VERIFY_TLS, timeout=10) as client:
            r = await client.post(token_url, data=payload, headers={"Content-Type":"application/x-www-form-urlencoded"})
        if r.status_code != 200:
            logger.warning("Keycloak password-grant failed | status=%s | username=%s", r.status_code, username)
            raise ValueError("Invalid credentials")

        tokens = r.json()
        user = await fetch_userinfo(tokens.get("access_token"))
        return user

async def fetch_userinfo(access_token: str | None) -> UserInfo:
    if not access_token:
        raise ValueError("Missing access token")
    userinfo_url = KeycloakProvider().base() + "/userinfo"
    async with httpx.AsyncClient(verify=settings.KEYCLOAK_VERIFY_TLS, timeout=10) as client:
        ur = await client.get(userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
    payload = ur.json() if ur.content else {}
    roles: List[str] = []
    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict):
        roles = realm_access.get("roles") or []
    return UserInfo(
        user_id=str(payload.get("sub") or payload.get("preferred_username") or "unknown"),
        username=payload.get("preferred_username") or payload.get("email") or "unknown",
        display_name=payload.get("name"),
        email=payload.get("email"),
        roles=roles,
        auth_source="keycloak",
    )
