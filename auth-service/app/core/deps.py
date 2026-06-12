from __future__ import annotations

from typing import Optional
from fastapi import Cookie, HTTPException, status

from app.core.config import get_settings
from app.services.session_store import session_store
from app.schemas.auth import UserInfo

settings = get_settings()


def get_current_user(
    session_cookie: Optional[str] = Cookie(default=None, alias=settings.SESSION_COOKIE_NAME),
) -> UserInfo:
    if not session_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHENTICATED",
                "message": "Missing session cookie",
                "details": {},
            },
        )

    rec = session_store.get(session_cookie)

    if not rec:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHENTICATED",
                "message": "Invalid or expired session",
                "details": {},
            },
        )

    # ✅ SOURCE OF TRUTH: session already stores a UserInfo
    user = getattr(rec, "user", None)

    if not isinstance(user, UserInfo):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHENTICATED",
                "message": "Invalid session payload",
                "details": {},
            },
        )

    return user
