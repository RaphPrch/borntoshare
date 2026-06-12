from __future__ import annotations

from typing import Optional

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class DirectorySnapshotGroup(Base, TimestampMixin):
    __tablename__ = "directory_snapshot_groups"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "external_id", name="uq_directory_snapshot_groups_snapshot_external"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("directory_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    dn: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    when_changed: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    usn_changed: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    snapshot = relationship("DirectorySnapshot", back_populates="groups", lazy="selectin")
