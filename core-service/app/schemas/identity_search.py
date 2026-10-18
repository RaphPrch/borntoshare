from __future__ import annotations

from pydantic import BaseModel, Field


class IdentitySearchRequest(BaseModel):
    query: str = Field(default="", max_length=190)
    limit: int = Field(default=25, ge=1, le=500)
    identity_source_id: int | None = Field(default=None, gt=0)
    principal_type: str = Field(default="all", max_length=16)
    base_dn: str | None = Field(default=None, max_length=1024)
    search_scope: str = Field(default="subtree", max_length=16)
