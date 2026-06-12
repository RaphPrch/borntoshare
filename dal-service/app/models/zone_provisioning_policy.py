from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ZoneProvisioningPolicy(Base, TimestampMixin):
    """Zone-level provisioning policy (GOLD V1++)."""

    __tablename__ = "zone_provisioning_policy"

    # One policy row per zone
    zone_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("zones.id", ondelete="CASCADE"),
        primary_key=True,
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    policy_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="ON_FIRST_ACCESS_REQUEST")

    # identity_default | zone_static
    ou_strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="identity_default")
    static_ou_dn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_ou_dn: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
