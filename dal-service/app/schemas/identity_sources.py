from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


IdentitySourceType = Literal["ad"]


class IdentitySourceCapabilities(BaseModel):
    auth: bool = True
    import_groups: bool = True
    snapshot_enabled: bool = False
    auth_mode: Literal["ntlm", "kerberos"] = "ntlm"


class IdentitySourceCreate(BaseModel):
    type: IdentitySourceType
    name: str = Field(..., min_length=1, max_length=190)
    domain_name: Optional[str] = Field(default=None, max_length=255)
    external_id: Optional[str] = Field(default=None, max_length=255)

    # AD
    protocol: Optional[Literal["ldap", "ldaps"]] = "ldaps"
    host: Optional[str] = Field(default=None, max_length=190)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    base_dn: Optional[str] = Field(default=None, max_length=512)
    bind_dn: Optional[str] = Field(default=None, max_length=512)
    bind_password: Optional[str] = None
    bind_password_ref: Optional[str] = Field(default=None, max_length=512)

    @field_validator("bind_password")
    @classmethod
    def forbid_bind_password_plaintext(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if str(value).strip():
            raise ValueError("Plaintext secrets are not allowed. Use bind_password_ref.")
        return None

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

    # OIDC
    issuer_url: Optional[str] = Field(default=None, max_length=512)

    capabilities: IdentitySourceCapabilities = Field(default_factory=IdentitySourceCapabilities)
    auth_enabled: bool = Field(default=False)
    auth_priority: int = Field(default=100, ge=0, le=10000)
    is_active: bool = True


class IdentitySourceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=190)
    domain_name: Optional[str] = Field(default=None, max_length=255)
    external_id: Optional[str] = Field(default=None, max_length=255)

    # AD
    protocol: Optional[Literal["ldap", "ldaps"]] = None
    host: Optional[str] = Field(default=None, max_length=190)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    base_dn: Optional[str] = Field(default=None, max_length=512)
    bind_dn: Optional[str] = Field(default=None, max_length=512)
    bind_password: Optional[str] = None
    bind_password_ref: Optional[str] = Field(default=None, max_length=512)

    @field_validator("bind_password")
    @classmethod
    def forbid_bind_password_plaintext(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if str(value).strip():
            raise ValueError("Plaintext secrets are not allowed. Use bind_password_ref.")
        return None

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

    # OIDC
    issuer_url: Optional[str] = Field(default=None, max_length=512)

    capabilities: Optional[IdentitySourceCapabilities] = None
    auth_enabled: Optional[bool] = None
    auth_priority: Optional[int] = Field(default=None, ge=0, le=10000)
    is_active: Optional[bool] = None


class IdentitySourceTestCheck(BaseModel):
    key: str
    ok: bool
    message: Optional[str] = None


class IdentitySourceTestResult(BaseModel):
    ok: bool
    checks: list[IdentitySourceTestCheck]
