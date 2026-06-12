from __future__ import annotations

from typing import Optional

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ProvisioningJob(Base, TimestampMixin):
    __tablename__ = "provisioning_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")

    storage_root_access_profile_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("storage_root_access_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    identity_source_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
