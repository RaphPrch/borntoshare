# app/schemas/zone.py
from __future__ import annotations

from typing import Optional
from pydantic import Field

from .common import WriteSchema


class ZoneCreate(WriteSchema):
    """
    Payload for creating a Zone.

    Note:
    - `code` may be omitted and generated server-side.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=190,
        description="Zone display name",
    )

    code: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Optional zone code",
    )

    description: Optional[str] = Field(
        default=None,
        description="Optional description",
    )

class ZoneUpdate(WriteSchema):
    """
    Partial update for a Zone.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=190,
    )

    code: Optional[str] = Field(
        default=None,
        max_length=64,
    )

    description: Optional[str] = None
