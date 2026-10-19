from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WriteSchema(BaseModel):
    """
    Base Pydantic for WRITE schemas (Create only).
    """

    model_config = ConfigDict(from_attributes=True)


class TimestampMixin(BaseModel):
    """
    Read-only timestamp fields (returned by the API).
    """

    created_at: Optional[datetime] = Field(
        default=None,
        description="Creation timestamp (read-only)",
        frozen=True,
    )

    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last update timestamp (read-only)",
        frozen=True,
    )


# Validation rules shared by several schemas (check_fields=False: each model declares its own fields)

class SecretRefRules(BaseModel):
    """Secrets are only accepted as sm:// references, never as plaintext."""

    @field_validator("bind_password", check_fields=False)
    @classmethod
    def forbid_bind_password_plaintext(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if str(value).strip():
            raise ValueError("Plaintext secrets are not allowed. Use bind_password_ref.")
        return None

    @field_validator("bind_password_ref", check_fields=False)
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


class ProbeStatusRules(BaseModel):
    @field_validator("last_probe_status", check_fields=False)
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
