"""SSO providers for auth-service (internal): login buttons, configuration, access decision."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.internal_auth import require_internal
from app.services import sso_service
from app.services.activity_log import log_activity

router = APIRouter(
    prefix="/internal/sso-providers",
    tags=["internal-sso"],
    dependencies=[require_internal({"jobs:read"})],
)


@router.get("")
def list_enabled_providers(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Buttons of the login page."""
    rows = db.execute(text("SELECT id, name, button_label FROM sso_providers WHERE is_enabled = 1 ORDER BY name")).mappings()
    return {"providers": [{"id": int(r["id"]), "name": r["name"], "label": r["button_label"] or r["name"]} for r in rows]}


@router.get("/{provider_id}")
def get_provider_config(provider_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = sso_service.get_provider_row(db, provider_id)
    if not row or not row.get("is_enabled"):
        raise HTTPException(status_code=404, detail="SSO provider not found or disabled")
    return {
        **sso_service.provider_public(row),
        "client_secret_ref": row.get("client_secret_ref"),
        "role_mapping": sso_service._json(row.get("role_mapping_json")) or [],
    }


class SsoClaims(BaseModel):
    sub: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    roles: list[str] = Field(default_factory=list, max_length=500)


@router.post("/{provider_id}/resolve-identity")
def resolve_identity(provider_id: int, claims: SsoClaims, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = sso_service.resolve_sso_identity(db, provider_id=provider_id, claims=claims.model_dump())
    db.commit()
    if result.get("linked") == "created":
        log_activity(
            db,
            actor_type="system",
            actor_id=None,
            actor_display="auth-service",
            action="identity.account_created",
            outcome="success",
            target_type="identity",
            target_id=result["identity_id"],
            target_display=claims.name or claims.username,
            context_json={"provisioning_source": "sso", "sso_provider_id": provider_id, "roles": result.get("roles")},
        )
    return result
