from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AccessRequestItemCreate(BaseModel):
    target_type: str = Field(..., min_length=1, max_length=32)
    target_id: int = Field(..., gt=0)
    permission: str = Field(..., min_length=1, max_length=32)
    expires_at: Optional[datetime] = None
