from __future__ import annotations

from typing import Optional

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class DirectorySnapshotUser(Base, TimestampMixin):
    __tablename__ = "directory_snapshot_users"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "external_id", name="uq_directory_snapshot_users_snapshot_external"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("directory_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    object_guid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    object_sid: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    upn: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dn: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    when_changed: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    usn_changed: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    snapshot = relationship("DirectorySnapshot", back_populates="users", lazy="selectin")
