from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import Field

from .common import ProbeStatusRules, SecretRefRules, WriteSchema


# ============================================================
# CREATE
# ============================================================

class StorageEndpointCreate(SecretRefRules, ProbeStatusRules, WriteSchema):
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



# ============================================================
# UPDATE (PATCH semantics)
# ============================================================

class StorageEndpointUpdate(SecretRefRules, ProbeStatusRules):
    """
    Partial update for a StorageEndpoint (PATCH semantics).
    All fields are optional.
    """

    # --------------------------------------------------
    # Identity
    # --------------------------------------------------

    # Host change of a file server that has storage roots: rewrite their UNC paths to the new host
    rewrite_root_paths: Optional[bool] = None

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

