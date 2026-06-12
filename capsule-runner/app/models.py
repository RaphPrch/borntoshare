from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal

# Runner scope is a DEPLOYMENT SAFETY CONTROL, not user RBAC.
Scope = Literal["read", "write", "admin"]


# -------------------------------
# Runner v1 contract
# -------------------------------
class TemplateRef(BaseModel):
    slug: str = Field(..., min_length=1, description="Template identifier, e.g. 'test_smb_ntlm'")
    version: str = Field("v1", min_length=1, description="Template version, e.g. 'v1'")


class SecretItem(BaseModel):
    # V1 (Community): Internal secret-broker resolves secrets and passes VALUES to the runner.
    # The runner MUST NOT call any secret backend by itself.
    value: Optional[str] = Field(default=None, description="Resolved secret value (provided by internal secret-broker)")


class SecretsBundle(BaseModel):
    items: Dict[str, SecretItem] = Field(default_factory=dict, description="Secrets mapped by secret_ref keys")


class RunnerExecuteRequest(BaseModel):
    template: TemplateRef
    timeout_seconds: int = Field(60, ge=1, le=600)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    secrets: SecretsBundle = Field(default_factory=SecretsBundle)
    options: Dict[str, Any] = Field(default_factory=dict)


class RunnerExecuteResponse(BaseModel):
    status: Literal["success", "failed"]
    exit_code: int
    result: Dict[str, Any] | None = None
    logs: Dict[str, Any] | None = None
    metrics: Dict[str, Any] | None = None
    error: Dict[str, Any] | None = None
