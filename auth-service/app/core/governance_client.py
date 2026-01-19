from __future__ import annotations

from app.core.logging import get_logger
from app.schemas.auth import UserInfo

logger = get_logger(__name__)


async def resolve_roles_with_governance(user: UserInfo) -> UserInfo:
    """
    ROLE RESOLUTION — STRICT BDD SOURCE OF TRUTH

    RULE:
    - roles are already resolved by DAL
    - auth-service MUST NOT override them
    - governance is NOT involved in authentication
    """

    if not user.roles:
        # sécurité défensive, ne devrait jamais arriver
        logger.error(
            "[AUTH][ROLE] user has no roles from DAL",
            extra={
                "username": user.username,
                "source": user.auth_source,
            },
        )
        raise RuntimeError("Roles missing from DAL")

    logger.debug(
        "[AUTH][ROLE] roles accepted from DAL",
        extra={
            "username": user.username,
            "roles": user.roles,
        },
    )

    return user
