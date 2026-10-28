# app/schemas/tag.py
from __future__ import annotations

import hashlib
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Colors given to a tag created without one (same palette as the UI), chosen from its name
DEFAULT_TAG_COLORS = ("#2563eb", "#16a34a", "#9333ea", "#dc2626", "#0f766e", "#b45309", "#1d4ed8", "#6b7280")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def default_tag_color(name: str) -> str:
    digest = hashlib.sha1(str(name or "").strip().lower().encode()).digest()
    return DEFAULT_TAG_COLORS[digest[0] % len(DEFAULT_TAG_COLORS)]


def _normalize_color(value: Optional[str]) -> Optional[str]:
    color = str(value or "").strip()
    if not color:
        return None
    if not _COLOR_RE.match(color):
        raise ValueError("A color like #2563eb is expected")
    return color.lower()


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
        description="Tag color (#rrggbb); a color of the palette when omitted",
    )

    @field_validator("color")
    @classmethod
    def _color(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_color(value)

    @model_validator(mode="after")
    def _default_color(self) -> "TagCreate":
        if not self.color:
            self.color = default_tag_color(self.name)
        return self


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

    @field_validator("color")
    @classmethod
    def _color(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_color(value)
