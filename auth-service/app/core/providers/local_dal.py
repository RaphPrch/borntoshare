from __future__ import annotations
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.providers.base import AuthProvider
from app.schemas.auth import UserInfo

settings = get_settings()
logger = get_logger(__name__)


class AuthUnavailable(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class DalLocalProvider(AuthProvider):
    name = "local"

    async def authenticate(self, username: str, password: str) -> UserInfo:
        url = settings.DAL_URL.rstrip("/") + settings.DAL_VALIDATE_CREDENTIALS_PATH
        payload = {"username": username, "password": password}
        timeout = getattr(settings, "DAL_TIMEOUT_SECONDS", 5)

        logger.debug(
            "DAL auth call | provider=local | username=%s | url=%s",
            username,
            url,
        )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=payload)
        except httpx.RequestError as exc:
            logger.error(
                "DAL unreachable | provider=local | url=%s | err=%s",
                url,
                exc,
            )
            raise AuthUnavailable()

        if r.status_code != 200:
            logger.warning(
                "DAL auth failed | provider=local | status=%s | username=%s",
                r.status_code,
                username,
            )
            raise InvalidCredentials()

        data = r.json() if r.content else {}

        return UserInfo(
            user_id=str(data.get("identity_id") or data.get("id") or data.get("user_id") or username),
            username=data.get("username") or username,
            display_name=data.get("display_name"),
            email=data.get("email"),
            roles=data.get("roles") or [],
            auth_source="local",
        )

    async def change_password(
        self,
        username: str,
        current_password: str,
        new_password: str,
    ) -> None:
        url = settings.DAL_URL.rstrip("/") + settings.DAL_CHANGE_PASSWORD_PATH
        payload = {
            "username": username,
            "current_password": current_password,
            "new_password": new_password,
        }
        timeout = getattr(settings, "DAL_TIMEOUT_SECONDS", 5)

        logger.info("DAL change-password | provider=local | username=%s", username)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=payload)
        except httpx.RequestError as exc:
            logger.error("DAL unreachable | change-password | err=%s", exc)
            raise AuthUnavailable()

        if r.status_code != 200:
            logger.warning(
                "DAL change-password failed | status=%s | username=%s",
                r.status_code,
                username,
            )
            raise InvalidCredentials()
