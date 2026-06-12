# app/models/storage_root.py
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .storage_endpoint import StorageEndpoint
    from .tag import Tag



class StorageRoot(Base, TimestampMixin):
    __tablename__ = "storage_roots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    storage_endpoint_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("storage_endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )

    parent_storage_root_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("storage_roots.id", ondelete="SET NULL"),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(190), nullable=False)
    root_path: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_root_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    inherit_owners: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inherit_tags: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inherit_access_profiles: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    last_probe_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_probe_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_probe_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    last_discovery_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    needs_revalidation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revalidation_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    discovered_permissions_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    discovered_tree_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)

    # -----------------------
    # Relationships
    # -----------------------

    storage_endpoint: Mapped["StorageEndpoint"] = relationship(
        "StorageEndpoint",
        back_populates="storage_roots",
        lazy="selectin",
    )

    parent_storage_root: Mapped[Optional["StorageRoot"]] = relationship(
        "StorageRoot",
        remote_side=[id],
        lazy="selectin",
    )

    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary="storage_root_tags",
        back_populates="storage_roots",
        lazy="selectin",
    )
