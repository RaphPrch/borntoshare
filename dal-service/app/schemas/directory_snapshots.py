from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DirectorySnapshotRunRequest(BaseModel):
    identity_source_id: int = Field(..., gt=0)
    initiated_by: str | None = Field(default=None, max_length=190)
    snapshot_source: str | None = Field(default="governance", max_length=64)
    correlation_id: str | None = Field(default=None, max_length=128)
    mode: str | None = Field(default=None, max_length=32)
    force_full: bool = False
    deferred: bool = False


class DirectorySnapshotRunResponse(BaseModel):
    snapshot_id: int
    identity_source_id: int
    version: int
    status: str


class DirectorySnapshotActivateRequest(BaseModel):
    activated_by: str | None = Field(default=None, max_length=190)
    rebuild_effective_memberships: bool = True


class DirectorySnapshotStatusPatchRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)
    summary_json: dict | None = None
    error_message: str | None = None


class DirectorySnapshotItem(BaseModel):
    id: int
    identity_source_id: int
    version: int
    status: str
    snapshot_source: str | None = None
    initiated_by: str | None = None
    correlation_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    activated_at: datetime | None = None
    archived_at: datetime | None = None
    summary_json: dict | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DirectorySnapshotUserUpsert(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=255)
    object_guid: str | None = Field(default=None, max_length=36)
    object_sid: str | None = Field(default=None, max_length=190)
    upn: str | None = Field(default=None, max_length=255)
    dn: str | None = Field(default=None, max_length=512)
    when_changed: datetime | None = None
    usn_changed: int | None = Field(default=None, ge=0)
    username: str | None = Field(default=None, max_length=190)
    display_name: str | None = Field(default=None, max_length=190)
    email: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    is_active: bool = True


class DirectorySnapshotGroupUpsert(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=255)
    dn: str | None = Field(default=None, max_length=512)
    when_changed: datetime | None = None
    usn_changed: int | None = Field(default=None, ge=0)
    name: str | None = Field(default=None, max_length=255)
    code: str | None = Field(default=None, max_length=255)
    description: str | None = None
    is_active: bool = True


class DirectorySnapshotMembershipUpsert(BaseModel):
    group_external_id: str = Field(..., min_length=1, max_length=255)
    member_external_id: str = Field(..., min_length=1, max_length=255)
    member_type: str = Field(default="user", min_length=1, max_length=16)


class DirectorySnapshotBulkUpsertRequest(BaseModel):
    users: list[DirectorySnapshotUserUpsert] = Field(default_factory=list)
    groups: list[DirectorySnapshotGroupUpsert] = Field(default_factory=list)
    memberships: list[DirectorySnapshotMembershipUpsert] = Field(default_factory=list)
