from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

from app.schemas.common import SecretRefRules


IdentitySourceType = Literal["ad"]


class IdentitySourceCapabilities(BaseModel):
    auth: bool = True
    import_groups: bool = True
    snapshot_enabled: bool = False
    # Create AD groups and change their members (stored in identity_sources.write_enabled)
    provisioning: bool = False
    auth_mode: Literal["ntlm", "kerberos"] = "ntlm"


class ServiceAccountIn(BaseModel):
    """Dedicated account of a capability; an empty bind_dn removes it (back to the account of the source)."""

    bind_dn: Optional[str] = Field(default=None, max_length=512)
    bind_password_ref: Optional[str] = Field(default=None, max_length=512)


ServiceAccountPurpose = Literal["snapshot", "auth", "provisioning"]


class IdentitySourceCreate(SecretRefRules):
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

    # OIDC
    issuer_url: Optional[str] = Field(default=None, max_length=512)

    capabilities: IdentitySourceCapabilities = Field(default_factory=IdentitySourceCapabilities)
    service_accounts: Optional[dict[ServiceAccountPurpose, Optional[ServiceAccountIn]]] = None
    auth_enabled: bool = Field(default=False)
    auth_priority: int = Field(default=100, ge=0, le=10000)
    is_active: bool = True


class IdentitySourceUpdate(SecretRefRules):
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

    # OIDC
    issuer_url: Optional[str] = Field(default=None, max_length=512)

    capabilities: Optional[IdentitySourceCapabilities] = None
    service_accounts: Optional[dict[ServiceAccountPurpose, Optional[ServiceAccountIn]]] = None
    auth_enabled: Optional[bool] = None
    auth_priority: Optional[int] = Field(default=None, ge=0, le=10000)
    is_active: Optional[bool] = None
