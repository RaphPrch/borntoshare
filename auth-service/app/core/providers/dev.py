from __future__ import annotations
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.providers.base import AuthProvider
from app.schemas.auth import UserInfo

settings = get_settings()
logger = get_logger(__name__)

class DevProvider(AuthProvider):
    name = "dev"

    async def authenticate(self, username: str, password: str) -> UserInfo:
        if username != settings.DEV_USER_USERNAME or password != settings.DEV_USER_PASSWORD:
            logger.warning("DEV auth failed | username=%s", username)
            raise ValueError("Invalid credentials")

        logger.warning("DEV auth success | username=%s", username)
        return UserInfo(
            user_id="dev-user",
            username=settings.DEV_USER_USERNAME,
            display_name=settings.DEV_USER_DISPLAY_NAME,
            email=settings.DEV_USER_EMAIL,
            roles=settings.DEV_USER_ROLES,
            auth_source="dev",
        )
