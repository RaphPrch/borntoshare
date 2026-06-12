# app/models/tag.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .storage_root import StorageRoot


class Tag(Base, TimestampMixin):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(190),
        nullable=False,
    )

    color: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)

    # ============================================================
    # Relationships
    # ============================================================

    storage_roots: Mapped[list["StorageRoot"]] = relationship(
        "StorageRoot",
        secondary="storage_root_tags",
        back_populates="tags",
        lazy="selectin",
    )
