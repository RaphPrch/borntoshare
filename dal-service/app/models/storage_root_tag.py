"""
Association table between StorageRoot and Tag.

- Pure association table (no ORM model)
- Aligned with the canonical SQL schema:
  auto-increment technical id plus unique storage_root/tag pair
- Used via `secondary="storage_root_tags"`
"""

from sqlalchemy import Table, Column, BigInteger, DateTime, ForeignKey, Index, UniqueConstraint, func

from app.models.base import Base


storage_root_tag = Table(
    "storage_root_tags",
    Base.metadata,

    Column(
        "id",
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    ),

    Column(
        "storage_root_id",
        BigInteger,
        ForeignKey("storage_roots.id", ondelete="CASCADE"),
        nullable=False,
    ),

    Column(
        "tag_id",
        BigInteger,
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
    ),

    Column("created_at", DateTime(timezone=False), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now()),
    Column("deleted_at", DateTime(timezone=False), nullable=True),

    # ------------------------------------------------------------
    # Table options
    # ------------------------------------------------------------
    UniqueConstraint("storage_root_id", "tag_id", name="uq_storage_root_tags_storage_root_id_tag_id"),
    Index("ix_storage_root_tags_storage_root_id", "storage_root_id"),
    Index("ix_storage_root_tags_tag_id", "tag_id"),

    extend_existing=True,
    comment="Association between storage_root and tag (many-to-many)",
)
