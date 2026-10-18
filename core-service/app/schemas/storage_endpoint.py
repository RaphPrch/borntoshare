from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from .common import WriteSchema


# ============================================================
# CREATE
# ============================================================

class StorageEndpointCreate(WriteSchema):
    """
    Payload for creating a StorageEndpoint.
    """

    # --------------------------------------------------
    # Identity
    # --------------------------------------------------

    name: str = Field(
        ...,
        min_length=1,
        max_length=190,
        description="Storage endpoint display name",
    )

    endpoint_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Endpoint type (wizard-ui)",
    )

    # --------------------------------------------------
    # Foreign keys (optional)
    # --------------------------------------------------

    zone_id: int
    identity_source_id: Optional[int] = None

    # --------------------------------------------------
    # Endpoint definition
    # --------------------------------------------------

    protocol: Optional[str] = Field(default=None, max_length=16)
    host: Optional[str] = Field(default=None, max_length=190)
    port: Optional[int] = None
    sub_ou_dn: Optional[str] = Field(default=None, max_length=512)

    auth_type: Optional[str] = Field(default=None, max_length=32)
    bind_dn: Optional[str] = Field(default=None, max_length=512)
    bind_password_ref: Optional[str] = Field(default=None, max_length=512)

    @field_validator("bind_password_ref")
    @classmethod
    def validate_bind_password_ref(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        v = str(value).strip()
        if not v:
            return None
        if not v.startswith("sm://"):
            raise ValueError("bind_password_ref must start with sm://")
        return v

    capabilities: Optional[dict] = Field(default_factory=dict)
    description: Optional[str] = None
    external_id: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True

    # --------------------------------------------------
    # Authentication / provider
    # --------------------------------------------------

    status: Optional[str] = Field(
        default="active",
        max_length=32,
    )

    last_probe_job_id: Optional[int] = None
    last_probe_status: Optional[str] = Field(default=None, max_length=32)
    last_probe_at: Optional[datetime] = None
    last_probe_message: Optional[str] = Field(default=None, max_length=512)

    @field_validator("last_probe_status")
    @classmethod
    def validate_last_probe_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        key = str(value).strip().lower()
        if not key:
            return None
        if key in {"success", "running", "failed", "unknown"}:
            return key
        raise ValueError("last_probe_status must be one of: success, running, failed, unknown")


# ============================================================
# UPDATE (PATCH semantics)
# ============================================================

class StorageEndpointUpdate(BaseModel):
    """
    Partial update for a StorageEndpoint (PATCH semantics).
    All fields are optional.
    """

    # --------------------------------------------------
    # Identity
    # --------------------------------------------------

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=190,
    )

    endpoint_type: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
    )

    # --------------------------------------------------
    # Foreign keys
    # --------------------------------------------------

    zone_id: Optional[int] = None
    identity_source_id: Optional[int] = None

    # --------------------------------------------------
    # Endpoint definition
    # --------------------------------------------------

    protocol: Optional[str] = Field(default=None, max_length=16)
    host: Optional[str] = Field(default=None, max_length=190)
    port: Optional[int] = None
    sub_ou_dn: Optional[str] = Field(default=None, max_length=512)

    auth_type: Optional[str] = Field(default=None, max_length=32)
    bind_dn: Optional[str] = Field(default=None, max_length=512)
    bind_password_ref: Optional[str] = Field(default=None, max_length=512)

    @field_validator("bind_password_ref")
    @classmethod
    def validate_bind_password_ref(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        v = str(value).strip()
        if not v:
            return None
        if not v.startswith("sm://"):
            raise ValueError("bind_password_ref must start with sm://")
        return v

    capabilities: Optional[dict] = None
    description: Optional[str] = None
    external_id: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None

    # --------------------------------------------------
    # Authentication / provider
    # --------------------------------------------------

    status: Optional[str] = Field(
        default=None,
        max_length=32,
    )

    last_probe_job_id: Optional[int] = None
    last_probe_status: Optional[str] = Field(default=None, max_length=32)
    last_probe_at: Optional[datetime] = None
    last_probe_message: Optional[str] = Field(default=None, max_length=512)

    @field_validator("last_probe_status")
    @classmethod
    def validate_last_probe_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        key = str(value).strip().lower()
        if not key:
            return None
        if key in {"success", "running", "failed", "unknown"}:
            return key
        raise ValueError("last_probe_status must be one of: success, running, failed, unknown")
