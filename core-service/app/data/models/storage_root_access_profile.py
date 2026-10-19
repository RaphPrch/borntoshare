from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class StorageRootAccessProfile(Base, TimestampMixin):
    """AD group governing one access level (READ/WRITE) of a storage root.

    Created on the first approved request for that level, then reused.
    """

    __tablename__ = "storage_root_access_profiles"

    __table_args__ = (
        UniqueConstraint("storage_root_id", "access_level_code", name="uq_srap_root_level"),
        UniqueConstraint("storage_root_id", "group_name", name="uq_srap_root_group_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    storage_root_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("storage_roots.id", ondelete="CASCADE"),
        nullable=False,
    )
    access_level_code: Mapped[str] = mapped_column(String(16), nullable=False)
    group_name: Mapped[str] = mapped_column(String(128), nullable=False)
    group_external_id: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
