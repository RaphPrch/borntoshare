# app/models/identity.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .local_credential import LocalCredential
    from .access_request import AccessRequest


class Identity(Base, TimestampMixin):
    """
    Identity represents a human or technical user in BornToShare.

    IMPORTANT:
    - Runtime authorization source of truth is RBAC (`roles` / `identity_roles` / `v_identity_effective_roles`)
    """

    __tablename__ = "identities"

    # ============================================================
    # Primary key
    # ============================================================

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # ============================================================
    # Identity core
    # ============================================================

    username: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    display_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    source_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("identity_sources.id"),
        nullable=True,
    )

    type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="user",
    )

    external_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    auth_source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="external",
    )

    # ============================================================
    # Lifecycle / Security
    # ============================================================

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

    snapshot_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    snapshot_source: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    provisioning_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="explicit",
    )

    snapshot_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    last_snapshot_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ============================================================
    # Relationships
    # ============================================================

    # 1–1 local authentication
    local_credential: Mapped[Optional["LocalCredential"]] = relationship(
        "LocalCredential",
        back_populates="identity",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    

    # Access requests initiated by this identity
    access_requests: Mapped[list["AccessRequest"]] = relationship(
        "AccessRequest",
        back_populates="requester",
        foreign_keys="[AccessRequest.requester_identity_id]",
        lazy="selectin",
    )
