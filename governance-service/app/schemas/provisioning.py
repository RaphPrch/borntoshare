from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AccessProfileCreateIn(BaseModel):
    access_level: str = Field(..., min_length=1, max_length=32)
    rights: List[str] = Field(default_factory=list)


class ProvisioningCompleteIn(BaseModel):
    stage: str = Field(..., min_length=1, max_length=32)
    status: str = Field(..., min_length=1, max_length=32)
    group_external_id: Optional[str] = None
    group_dn: Optional[str] = None
    result_json: Optional[dict] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class EnsureAdGroupContextIn(BaseModel):
    storage_root_id: Optional[int] = Field(default=None, gt=0)
    access_profile_id: Optional[int] = Field(default=None, gt=0)
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


class DiscoverGroupUsersRecursiveIn(BaseModel):
    identity_source_id: Optional[int] = Field(default=None, gt=0)
    root_group_dn: str = Field(..., min_length=1, max_length=1024)
    max_depth: int = Field(default=10, ge=1, le=30)
    timeout: Optional[int] = Field(default=None, ge=1, le=30)
    verify_tls: Optional[bool] = None


class GovernanceEnvelope(BaseModel):
    status: str
    message: str
    data: Dict[str, object] = Field(default_factory=dict)
    error_code: Optional[str] = None
