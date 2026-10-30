from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

class ActivityEventCreate(BaseModel):
    action: str = Field(..., min_length=1, max_length=128)
    outcome: str = Field("success", min_length=1, max_length=16)
    severity: str | None = Field(default=None, min_length=1, max_length=20)

    actor_type: str = Field("system", min_length=1, max_length=16)
    actor_id: int | str | None = None
    actor_display: str | None = None

    target_type: str | None = Field(None, max_length=64)
    target_id: int | str | None = None
    target_display: str | None = None

    zone_id: int | str | None = None
    root_id: int | str | None = None
    endpoint_id: int | str | None = None
    source_service: str | None = None

    metadata_json: dict[str, Any] | None = None

    context_json: dict[str, Any] | None = None
    correlation_id: str | None = None
