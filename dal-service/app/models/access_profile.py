# app/models/access_profile.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin



class AccessProfile(Base, TimestampMixin):
    """
    Access abstraction defining a reusable permission set.

    Examples:
      - read_standard
      - write_standard
      - admin_data

    Scope:
      - template-only (V1)
    """

    __tablename__ = "access_profiles"

    # ============================================================
    # Primary key
    # ============================================================

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # ============================================================
    # Identity
    # ============================================================

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    permission: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="READ",
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
