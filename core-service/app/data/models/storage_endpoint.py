from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .storage_root import StorageRoot
    from .zone import Zone



class StorageEndpoint(Base, TimestampMixin):
    __tablename__ = "storage_endpoints"

    # ============================================================
    # Primary key
    # ============================================================

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # ============================================================
    # Foreign keys
    # ============================================================

    zone_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("zones.id", ondelete="CASCADE"),
        nullable=False,
    )

    identity_source_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("identity_sources.id", ondelete="SET NULL"),
        nullable=True,
    )


    # ============================================================
    # Identity
    # ============================================================

    name: Mapped[str] = mapped_column(
        String(190),
        nullable=False,
    )

    # ============================================================
    # Endpoint definition
    # ============================================================

    endpoint_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    protocol: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
    )

    host: Mapped[Optional[str]] = mapped_column(
        String(190),
        nullable=True,
    )

    port: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    base_path: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    sub_ou_dn: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    naming_template: Mapped[Optional[str]] = mapped_column(
        String(190),
        nullable=True,
    )

    auth_type: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )

    bind_dn: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    bind_password_ref: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    capabilities: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    external_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    last_probe_job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    last_probe_status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )

    last_probe_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_probe_message: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)

    # ============================================================
    # Relationships
    # ============================================================


    zone: Mapped["Zone"] = relationship(
        "Zone",
        lazy="select",
        back_populates="storage_endpoints",
    )


    storage_roots: Mapped[list["StorageRoot"]] = relationship(
        "StorageRoot",
        back_populates="storage_endpoint",
        lazy="select",
        cascade="all, delete-orphan",
    )
