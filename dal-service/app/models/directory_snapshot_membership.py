from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class DirectorySnapshotMembership(Base, TimestampMixin):
    __tablename__ = "directory_snapshot_memberships"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "group_external_id",
            "member_external_id",
            name="uq_directory_snapshot_memberships_snapshot_group_member",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("directory_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    group_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    member_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    member_type: Mapped[str] = mapped_column(String(16), nullable=False, default="user")

    snapshot = relationship("DirectorySnapshot", back_populates="memberships", lazy="selectin")

