"""Local accounts (the fallback access): the account and its password hash, read and rotated here only."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def local_account(db: Session, username: str) -> dict[str, Any] | None:
    """The identity with a local password, found by its login (case ignored): identity_id, username, display_name,
    email, is_active, auth_source, password_hash."""
    row = db.execute(
        text(
            """
            SELECT i.id AS identity_id, i.username, i.display_name, i.email, COALESCE(i.is_active, 0) AS is_active,
                   COALESCE(i.auth_source, '') AS auth_source, lc.password_hash
            FROM identities i JOIN local_credentials lc ON lc.identity_id = i.id
            WHERE LOWER(COALESCE(i.username, '')) = LOWER(:username)
            LIMIT 1
            """
        ),
        {"username": username},
    ).mappings().first()
    return dict(row) if row else None


def set_password_hash(db: Session, identity_id: int, password_hash: str, rotated_at: datetime) -> None:
    db.execute(
        text("""UPDATE local_credentials SET password_hash = :password_hash, password_version = 'b2s$v=1$bcrypt',
                last_rotated_at = :last_rotated_at WHERE identity_id = :identity_id"""),
        {"identity_id": int(identity_id), "password_hash": password_hash, "last_rotated_at": rotated_at},
    )
    db.commit()
