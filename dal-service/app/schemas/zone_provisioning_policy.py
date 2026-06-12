from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


OUStrategy = Literal["identity_default", "zone_static"]


class ZoneProvisioningPolicyBase(BaseModel):
    enabled: bool = False
    ou_strategy: OUStrategy = "identity_default"
    base_ou_dn: str | None = None
    static_ou_dn: str | None = None


class ZoneProvisioningPolicyUpdate(BaseModel):
    enabled: bool | None = None
    ou_strategy: OUStrategy | None = None
    base_ou_dn: str | None = None
    static_ou_dn: str | None = None


class EffectivePreview(BaseModel):
    effective_identity_source_id: int | None = None
    effective_identity_source_name: str | None = None
    effective_ou_dn: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ZoneProvisioningPolicyRead(ZoneProvisioningPolicyBase):
    effective_preview: EffectivePreview = Field(default_factory=EffectivePreview)
