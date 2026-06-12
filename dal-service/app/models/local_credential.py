# app/models/local_credential.py
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .identity import Identity


class LocalCredential(Base, TimestampMixin):
    """
    Local authentication credentials for an identity.

    - Strict 1-1 relationship with Identity
    - Uses the canonical SQL schema primary key plus a unique identity link
    """

    __tablename__ = "local_credentials"

    # ============================================================
    # Primary key
    # ============================================================

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    identity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("identities.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # ============================================================
    # Credentials
    # ============================================================

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    password_version: Mapped[str] = mapped_column(
        "password_version",
        String(32),
        nullable=False,
        default="b2s$v=1$bcrypt",
    )

    # ============================================================
    # Rotation metadata
    # ============================================================

    last_rotated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    # ============================================================
    # Relationships
    # ============================================================

    identity: Mapped["Identity"] = relationship(
        "Identity",
        back_populates="local_credential",
        uselist=False,
    )
