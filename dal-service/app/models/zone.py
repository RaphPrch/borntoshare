# app/models/zone.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .storage_endpoint import StorageEndpoint



class Zone(Base, TimestampMixin):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(String(190), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)


    # ============================================================
    # Relationships
    # ============================================================

    # via storage_endpoints.zone_id (FK côté storage_endpoint)
    storage_endpoints: Mapped[list["StorageEndpoint"]] = relationship(
        "StorageEndpoint",
        lazy="selectin",
        back_populates="zone",
    )
