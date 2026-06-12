from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class DirectoryEffectiveMembership(Base, TimestampMixin):
    __tablename__ = "directory_effective_memberships"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    identity_source_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("identity_sources.id", ondelete="CASCADE"),
        nullable=False,
    )

    snapshot_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("directory_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )

    directory_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    directory_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    path_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    resolution_type: Mapped[str] = mapped_column(String(32), nullable=False, default="direct")

