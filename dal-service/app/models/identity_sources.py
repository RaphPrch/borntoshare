from __future__ import annotations

from typing import Optional

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class IdentitySource(Base, TimestampMixin):
    """Identity source (AD / OIDC)."""

    __tablename__ = "identity_sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ad (single supported identity source type in V1)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(190), nullable=False)
    domain_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    write_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    default_group_ou_dn: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # AD
    protocol: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # ldap|ldaps
    host: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    base_dn: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    bind_dn: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    bind_password_ref: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # OIDC (Wizard-UI schema authority)
    issuer_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="disabled")
    last_probe_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_probe_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    last_snapshot_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_snapshot_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_usn_changed: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    last_dirsync_cookie: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snapshot_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="full")
    delta_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dirsync_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
