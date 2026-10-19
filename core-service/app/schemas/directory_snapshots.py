from __future__ import annotations


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

