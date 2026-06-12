from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AccessRequestItem(Base, TimestampMixin):
    __tablename__ = "access_request_items"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    access_request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("access_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    target_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    target_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    permission: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    expires_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime,
        nullable=True,
    )
