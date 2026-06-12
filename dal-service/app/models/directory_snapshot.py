from __future__ import annotations

from typing import Optional

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class DirectorySnapshot(Base, TimestampMixin):
    __tablename__ = "directory_snapshots"
    __table_args__ = (
        UniqueConstraint("identity_source_id", "version", name="uq_directory_snapshots_source_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    identity_source_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("identity_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    snapshot_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    initiated_by: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)

    summary_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    users = relationship(
        "DirectorySnapshotUser",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    groups = relationship(
        "DirectorySnapshotGroup",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    memberships = relationship(
        "DirectorySnapshotMembership",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
