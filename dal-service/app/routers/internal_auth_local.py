from __future__ import annotations

from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.security.internal_auth import require_service_token
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request


router = APIRouter(prefix="/internal/auth", tags=["internal-auth"])


def _actor_from_headers(request: Request) -> tuple[int | None, str | None]:
    actor = actor_from_request(request)
    return actor.identity_id, actor.display_name


def _normalize_password(password: str) -> bytes:
    raw = str(password or "").encode("utf-8")
    return raw[:72]


def _verify_b2s_password(password: str, stored_hash: str) -> bool:
    value = str(stored_hash or "").strip()
    if not value:
        return False

    if value.startswith("b2s$v=1$bcrypt$"):
        bcrypt_hash = value.split("b2s$v=1$bcrypt$", 1)[1]
    else:
        bcrypt_hash = value

    if not bcrypt_hash:
        return False

    try:
        return bcrypt.checkpw(_normalize_password(password), bcrypt_hash.encode("utf-8"))
    except Exception:
        return False


def _hash_b2s_password(password: str) -> str:
    digest = bcrypt.hashpw(_normalize_password(password), bcrypt.gensalt(rounds=12)).decode("utf-8")
    return f"b2s$v=1$bcrypt${digest}"


class LocalVerifyPayload(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=512)


class LocalChangePasswordPayload(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    current_password: str | None = Field(default=None, max_length=512)
    new_password: str = Field(..., min_length=1, max_length=512)


@router.post("/local/verify", dependencies=[Depends(require_service_token)])
def verify_local_credentials(payload: LocalVerifyPayload, db: Session = Depends(get_db)):
    row = db.execute(
        text(
            """
            SELECT
              i.id AS identity_id,
              i.username,
              i.display_name,
              i.email,
              COALESCE(i.is_active, 0) AS is_active,
              COALESCE(i.auth_source, '') AS auth_source,
              lc.password_hash
            FROM identities i
            JOIN local_credentials lc ON lc.identity_id = i.id
            WHERE LOWER(COALESCE(i.username, '')) = LOWER(:username)
            LIMIT 1
            """
        ),
        {"username": payload.username},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not bool(row.get("is_active")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if str(row.get("auth_source") or "").strip().lower() not in {"local", "internal"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not _verify_b2s_password(payload.password, str(row.get("password_hash") or "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return {
        "identity_id": str(int(row.get("identity_id") or 0)),
        "username": row.get("username") or payload.username,
        "display_name": row.get("display_name"),
        "email": row.get("email"),
    }


@router.post("/change-password", dependencies=[Depends(require_service_token)])
def change_local_password(
    payload: LocalChangePasswordPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    row = db.execute(
        text(
            """
            SELECT
              i.id AS identity_id,
              COALESCE(i.is_active, 0) AS is_active,
              COALESCE(i.auth_source, '') AS auth_source,
              lc.password_hash
            FROM identities i
            JOIN local_credentials lc ON lc.identity_id = i.id
            WHERE LOWER(COALESCE(i.username, '')) = LOWER(:username)
            LIMIT 1
            """
        ),
        {"username": payload.username},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not bool(row.get("is_active")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if str(row.get("auth_source") or "").strip().lower() not in {"local", "internal"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    current_password = str(payload.current_password or "")
    if current_password and not _verify_b2s_password(current_password, str(row.get("password_hash") or "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(
        text(
            """
            UPDATE local_credentials
            SET password_hash = :password_hash,
                password_version = 'b2s$v=1$bcrypt',
                last_rotated_at = :last_rotated_at
            WHERE identity_id = :identity_id
            """
        ),
        {
            "identity_id": int(row.get("identity_id") or 0),
            "password_hash": _hash_b2s_password(payload.new_password),
            "last_rotated_at": now,
        },
    )
    db.commit()

    actor_id, actor_display = _actor_from_headers(request)
    target_id = int(row.get("identity_id") or 0)
    target_display = str(payload.username or "").strip() or None
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id if actor_id is not None else target_id,
        actor_display=actor_display or target_display,
        action="identity.password_changed",
        outcome="success",
        target_type="identity",
        target_id=target_id,
        target_display=target_display,
        context_json={"updated_fields": ["password"]},
        correlation_id=(request.headers.get("x-request-id") or None),
    )

    return {"ok": True}
