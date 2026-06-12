from __future__ import annotations

from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from .access_request_item import AccessRequestItemCreate

from .common import WriteSchema


# ============================================================
# CREATE
# ============================================================

class AccessRequestCreate(WriteSchema):
    """
    Create a new access request.

    V1:
    - requested_access: read | write
    """

    code: Optional[str] = Field(default=None, min_length=1, max_length=32)

    requester_identity_id: Optional[int] = None

    context_snapshot_at: Optional[datetime] = None

    # UI payload (frontend)
    storage_root_id: Optional[int] = Field(default=None, gt=0)
    permissions: Optional[list[str]] = None
    justification: Optional[str] = Field(default=None, max_length=2000)
    expires_at: Optional[datetime] = None
    requested_principal: Optional[dict[str, Any]] = None

    items: list[AccessRequestItemCreate] = Field(default_factory=list)


# ============================================================
# UPDATE (PATCH semantics)
# ============================================================

class AccessRequestUpdate(BaseModel):
    """
    Partial update for an access request.

    Allowed transitions handled by governance layer.
    """

    status: Optional[str] = Field(
        default=None,
        max_length=32,
    )
