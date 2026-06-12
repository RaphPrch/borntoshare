from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IdentitySourcePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str | None = None
    bind_password_ref: str | None = None


class ADSecretUpsertPayload(IdentitySourcePayload):
    bind_password: str | None = Field(default=None, repr=False)


class ADIdentitySourceTestPayload(IdentitySourcePayload):
    host: str
    base_dn: str
    bind_dn: str
