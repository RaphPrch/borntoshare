from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class WriteSchema(BaseModel):
    """
    Base Pydantic for WRITE schemas (Create only).
    """

    model_config = ConfigDict(from_attributes=True)


class TimestampMixin(BaseModel):
    """
    Read-only timestamp fields (returned by the API).
    """

    created_at: Optional[datetime] = Field(
        default=None,
        description="Creation timestamp (read-only)",
        frozen=True,
    )

    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last update timestamp (read-only)",
        frozen=True,
    )


class ApiMeta(BaseModel):
    """Standard metadata block for UI envelopes."""

    model_config = ConfigDict(extra="allow")

    count: int | None = Field(default=None, description="Number of elements in current payload")
    total: int | None = Field(default=None, description="Total number of elements available")
    request_id: str | None = Field(default=None, description="Request identifier propagated by middleware")


class ApiEnvelope(BaseModel, Generic[T]):
    """Standard envelope for a single payload."""

    data: T
    meta: ApiMeta = Field(default_factory=ApiMeta)


class ApiListEnvelope(BaseModel, Generic[T]):
    """Standard envelope for list payloads."""

    data: list[T] = Field(default_factory=list)
    meta: ApiMeta = Field(default_factory=ApiMeta)


class ApiActionResult(BaseModel):
    """Standard envelope payload for action endpoints."""

    ok: bool = True
    id: int | str | None = None
    message: str | None = None
    details: dict[str, Any] | None = None
