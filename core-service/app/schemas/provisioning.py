from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EnsureAdGroupContextIn(BaseModel):
    storage_root_id: Optional[int] = Field(default=None, gt=0)
    storage_root_access_profile_id: Optional[int] = Field(default=None, gt=0)
    zone_id: Optional[int] = Field(default=None, gt=0)


class EnsureAdGroupIn(BaseModel):
    group_name: str = Field(..., min_length=1, max_length=128)
    target_ou_dn: Optional[str] = Field(default=None, max_length=1024)
    directory_server_hint: Optional[str] = Field(default=None, max_length=255)
    description_text: Optional[str] = Field(default=None, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, max_length=512)
    identity_source_id: Optional[int] = Field(default=None, gt=0)
    domain_name: Optional[str] = Field(default=None, max_length=255)
    context: Optional[EnsureAdGroupContextIn] = None


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

