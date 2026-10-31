# app/schemas/zone.py
from __future__ import annotations

import re

from typing import Optional
from pydantic import Field, field_validator

from .common import WriteSchema


ZONE_CODE = re.compile(r"^[A-Za-z0-9._-]+$")


def _clean_zone_code(value: Optional[str]) -> Optional[str]:
    code = (value or "").strip()
    if not code:
        return None
    if not ZONE_CODE.match(code):
        raise ValueError("Le code de la zone ne peut contenir que des lettres, des chiffres, des points, des tirets et des tirets bas.")
    return code


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

    @field_validator("code")
    @classmethod
    def _code(cls, value: Optional[str]) -> Optional[str]:
        return _clean_zone_code(value)

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

    @field_validator("code")
    @classmethod
    def _code(cls, value: Optional[str]) -> Optional[str]:
        return _clean_zone_code(value)
