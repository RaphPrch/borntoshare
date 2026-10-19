# app/schemas/tag.py
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ============================================================
# CREATE
# ============================================================

class TagCreate(BaseModel):
    """
    Payload for creating a Tag.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=190,
        description="Short name for the tag",
    )

    color: Optional[str] = Field(
        default=None,
        max_length=32,
        description="Optional tag color",
    )


# ============================================================
# UPDATE (PATCH semantics)
# ============================================================

class TagUpdate(BaseModel):
    """
    Partial update for a Tag (PATCH semantics).
    All fields are optional.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=190,
        description="Short name for the tag",
    )

    color: Optional[str] = Field(
        default=None,
        max_length=32,
        description="Optional tag color",
    )
