from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ============================================================
# CREATE
# ============================================================

class StorageRootCreate(BaseModel):
    """
    Payload for creating a StorageRoot.
    WRITE MODEL ONLY.
    """

    # --------------------------------------------------
    # Technical attachment (mandatory)
    # --------------------------------------------------

    storage_endpoint_id: int = Field(
        ...,
        gt=0,
        description="Parent storage endpoint ID",
    )

    parent_storage_root_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional managed parent storage root. If omitted, DAL resolves it from root_path.",
    )

    # --------------------------------------------------
    # Logical attachment
    # --------------------------------------------------


    # --------------------------------------------------
    # Identity
    # --------------------------------------------------

    name: str = Field(
        ...,
        min_length=1,
        max_length=190,
        description="Storage root display name",
    )

    root_path: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Filesystem path or resource root",
    )

    inherit_owners: bool = Field(
        default=False,
        description="Whether owners may be inherited from parent storage root.",
    )

    inherit_tags: bool = Field(
        default=False,
        description="Whether tags may be inherited from parent storage root.",
    )

    inherit_access_profiles: bool = Field(
        default=False,
        description="Whether access profile bindings may be inherited from parent storage root.",
    )

    # --------------------------------------------------
    # Lifecycle
    # --------------------------------------------------

    status: Optional[str] = Field(
        default="active",
        description="Storage root status",
    )


# ============================================================
# UPDATE (PATCH semantics)
# ============================================================

class StorageRootUpdate(BaseModel):
    """
    Partial update for a StorageRoot (PATCH semantics).
    WRITE MODEL ONLY.
    """

    # --------------------------------------------------
    # Technical attachment
    # --------------------------------------------------

    storage_endpoint_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Change parent storage endpoint",
    )

    parent_storage_root_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional managed parent storage root. Explicit null clears the parent.",
    )

    # --------------------------------------------------
    # Logical attachment
    # --------------------------------------------------


    # --------------------------------------------------
    # Identity
    # --------------------------------------------------

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=190,
    )

    root_path: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=512,
    )

    inherit_owners: Optional[bool] = Field(default=None)

    inherit_tags: Optional[bool] = Field(default=None)

    inherit_access_profiles: Optional[bool] = Field(default=None)

    # --------------------------------------------------
    # Lifecycle
    # --------------------------------------------------

    status: Optional[str] = Field(
        default=None,
    )

    last_probe_status: Optional[str] = Field(
        default=None,
        max_length=32,
    )

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

    last_probe_at: Optional[datetime] = None

    last_probe_message: Optional[str] = Field(
        default=None,
        max_length=512,
    )

    needs_revalidation: Optional[bool] = None

    revalidation_reason: Optional[str] = Field(
        default=None,
        max_length=512,
    )
