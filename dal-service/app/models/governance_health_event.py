from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class GovernanceHealthEvent(Base, TimestampMixin):
    __tablename__ = "governance_health_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    job_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
