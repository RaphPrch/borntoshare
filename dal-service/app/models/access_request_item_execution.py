from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AccessRequestItemExecution(Base, TimestampMixin):
    __tablename__ = "access_request_item_executions"

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

    access_request_item_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("access_request_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING",
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    requested_payload_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )

    result_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )

    started_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    finished_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime,
        nullable=True,
    )
