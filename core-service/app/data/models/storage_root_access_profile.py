from __future__ import annotations

from typing import Optional

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class StorageRootAccessProfile(Base, TimestampMixin):
    __tablename__ = "storage_root_access_profiles"

    __table_args__ = (
        UniqueConstraint("storage_root_id", "access_profile_id", name="uq_srap_root_profile"),
        UniqueConstraint("storage_root_id", "group_name", name="uq_srap_root_group_name"),
        UniqueConstraint("storage_root_id", "permission_hash", name="uq_srap_root_permission_hash"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    storage_root_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("storage_roots.id", ondelete="CASCADE"),
        nullable=False,
    )

    access_profile_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("access_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(16), nullable=False, default="LOCAL")
    group_name: Mapped[str] = mapped_column(String(128), nullable=False)
    group_external_id: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)

    name: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    access_level_code: Mapped[str] = mapped_column(String(32), nullable=False, default="READ")
    permission_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    capsule_execution_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
