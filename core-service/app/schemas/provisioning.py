from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EnsureAdGroupMemberIn(BaseModel):
    identity_source_id: Optional[int] = Field(default=None, gt=0)
    group_ref: str = Field(..., min_length=1, max_length=1024)
    principal_dn: Optional[str] = Field(default=None, max_length=1024)
    principal_username: Optional[str] = Field(default=None, max_length=320)
    timeout: Optional[int] = Field(default=None, ge=1, le=30)
    verify_tls: Optional[bool] = None


class RemoveAdGroupMemberIn(BaseModel):
    identity_source_id: Optional[int] = Field(default=None, gt=0)
    group_ref: str = Field(..., min_length=1, max_length=1024)
    principal_dn: Optional[str] = Field(default=None, max_length=1024)
    principal_username: Optional[str] = Field(default=None, max_length=320)
    timeout: Optional[int] = Field(default=None, ge=1, le=30)
    verify_tls: Optional[bool] = None

