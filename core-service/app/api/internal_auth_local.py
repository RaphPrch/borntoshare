from __future__ import annotations

from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.data.repositories import local_credentials_repo
from app.core.db import get_db
from app.core.internal_auth import require_internal_token
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
    # Local accounts are the fallback access: a long password (the interface asks for the same)
    new_password: str = Field(..., min_length=12, max_length=512)


@router.post("/local/verify", dependencies=[Depends(require_internal_token)])
def verify_local_credentials(payload: LocalVerifyPayload, db: Session = Depends(get_db)):
    row = local_credentials_repo.local_account(db, payload.username)

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
        # A temporary password (the first administrator, set by the installation wizard): changed before anything else
        "must_change_password": bool(row.get("must_change_password")),
    }


@router.post("/change-password", dependencies=[Depends(require_internal_token)])
def change_local_password(
    payload: LocalChangePasswordPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    row = local_credentials_repo.local_account(db, payload.username)

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
    if current_password and _verify_b2s_password(payload.new_password, str(row.get("password_hash") or "")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "error_code": "PASSWORD_UNCHANGED", "message": "The new password must differ from the current one"})
    local_credentials_repo.set_password_hash(db, int(row.get("identity_id") or 0), _hash_b2s_password(payload.new_password), now,
                                             chosen_by_owner=bool(current_password))

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
