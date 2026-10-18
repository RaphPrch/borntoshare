from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class TagAttachmentRequest(BaseModel):
    tag_id: int = Field(..., gt=0)
    resource_type: Literal["storage_root"]
    resource_id: int = Field(..., gt=0)
