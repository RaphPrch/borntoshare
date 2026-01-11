from __future__ import annotations

from typing import Optional
from fastapi import Cookie, HTTPException, status

from app.core.session_store import session_store
from app.schemas.auth import UserInfo


def get_current_user(
    b2s_session: Optional[str] = Cookie(default=None),
) -> UserInfo:
    if not b2s_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing session cookie",
        )

    rec = session_store.get(b2s_session)

    if not rec:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    # ---- Mapping STRICT selon UserInfo ----

    # username peut être sur rec.username ou rec.user
    username = getattr(rec, "username", None) or getattr(rec, "user", None)

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session payload (missing username)",
        )

    return UserInfo(
        user_id=str(getattr(rec, "user_id", username)),  # V1: user_id == username si absent
        username=str(username),
        roles=list(getattr(rec, "roles", [])),
        auth_source=str(getattr(rec, "provider", "local")),
    )
