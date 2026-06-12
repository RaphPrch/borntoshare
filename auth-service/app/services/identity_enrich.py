from __future__ import annotations

from app.schemas.auth import UserInfo


def enrich_user_flags(user: UserInfo) -> UserInfo:
    """
    Normalize identity payload.

    V1:
    - No roles/permissions enrichment
    """
    return user
