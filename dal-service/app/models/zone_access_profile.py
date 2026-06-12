from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ZoneAccessProfile(Base, TimestampMixin):
    __tablename__ = "zone_access_profiles"

    zone_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("zones.id", ondelete="CASCADE"),
        primary_key=True,
    )

    access_profile_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("access_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

