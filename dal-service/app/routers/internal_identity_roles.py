from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.security.internal_auth import require_internal
from app.repositories.identity_roles_repo import IdentityRolesRepo


router = APIRouter(
    prefix="/internal/identities",
    tags=["internal-identity-roles"],
    dependencies=[require_internal({"jobs:read"})],
)


class IdentityRolesResponse(BaseModel):
    identity_id: str
    roles: List[str]


@router.get(
    "/{identity_id}/roles",
    response_model=IdentityRolesResponse,
    summary="Get effective roles for an identity (internal)",
)
def get_identity_effective_roles(
    identity_id: int,
    db: Session = Depends(get_db),
) -> IdentityRolesResponse:
    repo = IdentityRolesRepo(db)
    roles = repo.get_effective_role_codes(identity_id=identity_id)
    return IdentityRolesResponse(identity_id=str(identity_id), roles=roles)
