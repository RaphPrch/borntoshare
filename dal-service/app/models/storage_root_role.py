from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

if TYPE_CHECKING:
    from .storage_root import StorageRoot
    from .identity import Identity


class StorageRootRole(Base):
    __tablename__ = "storage_root_roles"
    __table_args__ = (
        UniqueConstraint("root_id", "identity_id", "role", name="uq_root_identity_role"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    root_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("storage_roots.id", ondelete="CASCADE"),
        nullable=False,
    )

    identity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("identities.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(String(16), nullable=False)

    assigned_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("identities.id", ondelete="SET NULL"),
        nullable=True,
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
