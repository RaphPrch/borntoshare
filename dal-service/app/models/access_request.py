# app/models/access_request.py
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .identity import Identity


class AccessRequest(Base, TimestampMixin):
    """
    Access request submitted by a user.
    """

    __tablename__ = "access_requests"

    # ============================================================
    # Primary key
    # ============================================================

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    requester_identity_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("identities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    decision_comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    decided_at: Mapped[Optional[str]] = mapped_column(
        DateTime,
        nullable=True,
    )

    revoked_at: Mapped[Optional[str]] = mapped_column(
        DateTime,
        nullable=True,
    )

    directory_snapshot_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    context_snapshot_at: Mapped[Optional[str]] = mapped_column(
        DateTime,
        nullable=True,
    )

    requested_principal_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )

    # ============================================================
    # Relationships
    # ============================================================

    requester: Mapped[Optional["Identity"]] = relationship(
        "Identity",
        back_populates="access_requests",
        lazy="selectin",
        foreign_keys=[requester_identity_id],
    )
