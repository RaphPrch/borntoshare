# app/models/base.py
from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, func


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """
    Standard timestamp mixin.

    - created_at: set by DB on INSERT
    - updated_at: set by DB on INSERT and UPDATE
    - DATETIME(6) in MySQL/MariaDB (timezone-naive, UTC by convention)
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
