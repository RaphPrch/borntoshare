from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    ok: bool = False
    data: None = None
    meta: dict = Field(default_factory=dict)
    error: ErrorBody


class ResolveRequest(BaseModel):
    ref: Optional[str] = Field(default=None, description="Secret reference (preferred)")


class SecretStoreData(BaseModel):
    ref: str


class SecretResolveData(BaseModel):
    value: str


class SecretRotateData(BaseModel):
    ref: str


class SecretRevokeData(BaseModel):
    ref: str
    revoked: bool


class SecretExistsData(BaseModel):
    ref: str
    exists: bool


class ResolveResponse(BaseModel):
    ok: bool = True
    data: SecretResolveData
    meta: dict = Field(default_factory=dict)
    error: None = None


class StoreResponse(BaseModel):
    ok: bool = True
    data: SecretStoreData
    meta: dict = Field(default_factory=dict)
    error: None = None


class RotateResponse(BaseModel):
    ok: bool = True
    data: SecretRotateData
    meta: dict = Field(default_factory=dict)
    error: None = None


class RevokeResponse(BaseModel):
    ok: bool = True
    data: SecretRevokeData
    meta: dict = Field(default_factory=dict)
    error: None = None


class ExistsResponse(BaseModel):
    ok: bool = True
    data: SecretExistsData
    meta: dict = Field(default_factory=dict)
    error: None = None
