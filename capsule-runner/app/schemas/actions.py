from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SMBProbePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    port: int = Field(default=445, ge=1, le=65535)
    timeout: int = Field(default=10, ge=1, le=30)
    discover: bool = False
    storage_endpoint_id: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_secret_or_password(self) -> "SMBProbePayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        return self


class SMBRootProbePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    share: str = Field(min_length=1, max_length=255)
    path: str = Field(default="", max_length=1024)
    username: str = Field(min_length=1, max_length=255)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    port: int = Field(default=445, ge=1, le=65535)
    timeout: int = Field(default=10, ge=1, le=30)
    storage_endpoint_id: Optional[int] = Field(default=None, gt=0)
    storage_root_id: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_secret_or_password(self) -> "SMBRootProbePayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        return self


class LDAPTestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=512)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    port: int = Field(default=389, ge=1, le=65535)
    timeout: int = Field(default=5, ge=1, le=15)
    use_ssl: bool = False
    verify_tls: bool = False

    @model_validator(mode="after")
    def _check_secret_or_password(self) -> "LDAPTestPayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        return self


class LDAPSearchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=512)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    base_dn: str = Field(min_length=1, max_length=1024)
    query: str = Field(default="", max_length=255)
    principal_type: Literal["all", "user", "group"] = "all"
    limit: int = Field(default=25, ge=1, le=5000)
    port: int = Field(default=389, ge=1, le=65535)
    timeout: int = Field(default=5, ge=1, le=15)
    use_ssl: bool = False

    @model_validator(mode="after")
    def _check_secret_or_password(self) -> "LDAPSearchPayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        return self


class DirectorySnapshotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: int = Field(..., gt=0)
    identity_source_id: int = Field(..., gt=0)
    host: str = Field(min_length=1, max_length=255)
    bind_dn: str = Field(min_length=1, max_length=1024)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    base_dn: str = Field(min_length=1, max_length=1024)
    protocol: str = Field(default="ldaps", min_length=4, max_length=16)
    port: int = Field(default=636, ge=1, le=65535)
    timeout: int = Field(default=15, ge=1, le=30)
    use_ssl: bool = True
    verify_tls: bool = False
    mode: str = Field(default="auto", min_length=1, max_length=32)
    force_full: bool = True

    @model_validator(mode="after")
    def _check_secret_or_password(self) -> "DirectorySnapshotPayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        return self


class KerberosAuthPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal: str = Field(min_length=1, max_length=512)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    realm: Optional[str] = Field(default=None, min_length=1, max_length=255)
    timeout: int = Field(default=7, ge=1, le=20)

    @model_validator(mode="after")
    def _check_secret_or_password(self) -> "KerberosAuthPayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        return self


class ADGroupCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_name: str = Field(min_length=1, max_length=128)
    target_ou_dn: str = Field(min_length=1, max_length=1024)
    host: Optional[str] = Field(default=None, min_length=1, max_length=255)
    bind_dn: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    username: Optional[str] = Field(default=None, min_length=1, max_length=512)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    protocol: str = Field(default="ldaps", min_length=4, max_length=16)
    port: int = Field(default=636, ge=1, le=65535)
    timeout: int = Field(default=5, ge=1, le=15)
    verify_tls: bool = False
    description_text: Optional[str] = Field(default=None, max_length=1024)
    domain_name: Optional[str] = Field(default=None, max_length=255)
    identity_source: Dict[str, Any] = Field(default_factory=dict)
    effective_group_ou_dn: Optional[str] = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _check_secret_or_password(self) -> "ADGroupCreatePayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        return self


class ADGroupMemberPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    bind_dn: str = Field(min_length=1, max_length=1024)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    protocol: str = Field(default="ldaps", min_length=4, max_length=16)
    port: int = Field(default=636, ge=1, le=65535)
    timeout: int = Field(default=5, ge=1, le=30)
    verify_tls: bool = False
    base_dn: str = Field(min_length=1, max_length=1024)
    group_ref: str = Field(min_length=1, max_length=1024)
    principal_dn: Optional[str] = Field(default=None, max_length=1024)
    principal_username: Optional[str] = Field(default=None, max_length=320)

    @model_validator(mode="after")
    def _check_identity_and_secret(self) -> "ADGroupMemberPayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        if not self.principal_dn and not self.principal_username:
            raise ValueError("principal_dn or principal_username is required")
        return self


class LDAPRecursiveGroupUsersPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    bind_dn: str = Field(min_length=1, max_length=1024)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    protocol: str = Field(default="ldaps", min_length=4, max_length=16)
    port: int = Field(default=636, ge=1, le=65535)
    timeout: int = Field(default=5, ge=1, le=30)
    verify_tls: bool = False
    base_dn: str = Field(min_length=1, max_length=1024)
    root_group_dn: str = Field(min_length=1, max_length=1024)
    max_depth: int = Field(default=10, ge=1, le=30)

    @model_validator(mode="after")
    def _check_secret_or_password(self) -> "LDAPRecursiveGroupUsersPayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        return self


class ACLApplyOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = False
    timeout_sec: int = Field(default=20, ge=1, le=60)


class ACLApplyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    share: str = Field(min_length=1, max_length=255)
    path: str = Field(default="", max_length=1024)
    ad_group_name: str = Field(min_length=1, max_length=255)
    permission: Literal["read", "write", "audit"]
    username: str = Field(min_length=1, max_length=255)
    password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    secret_ref: Optional[str] = Field(default=None, min_length=5, max_length=512)
    domain: str = Field(default="", max_length=255)
    options: ACLApplyOptions = Field(default_factory=ACLApplyOptions)
    timeout_sec: int = Field(default=20, ge=1, le=60)

    @model_validator(mode="after")
    def _check_secret_or_password(self) -> "ACLApplyPayload":
        if not self.password and not self.secret_ref:
            raise ValueError("password or secret_ref is required")
        return self
