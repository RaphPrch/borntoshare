"""Access Explorer (Access Management › Explorer): what a person or a group reaches and why, for administrators and guardians.
A folder has its own Permissions tab (its sheet in Storage Roots): the Explorer does not repeat it.

A guardian sees their own folders only: the folders listed are filtered, a folder outside them is refused, and a
user or a group reaching none of them is « not found » (the directory is not browsed through this page).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import features
from app.services.access_explorer import AccessExplorer
from app.services.authorization import actor_from_request, admin_or_guardian, require_storage_root_access

router = APIRouter(prefix="/access-explorer", tags=["access-explorer"], dependencies=[Depends(admin_or_guardian)])


def _explorer(request: Request, db: Session) -> AccessExplorer:
    # Part of the access governance (its menu entry too): not served on a 5S-only installation
    features.require(db, "governance")
    return AccessExplorer(db, actor_from_request(request))


def _found(value):
    if value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return value


@router.get("/search")
def search(
    request: Request,
    mode: Literal["user", "group"],
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Autocomplete and results of the four modes, paged."""
    return ui_data(_explorer(request, db).search(mode, q, offset, limit))


@router.get("/users/{user_id}")
def user_access(
    user_id: int,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    include_broad: bool = False,
    storage_root_id: int | None = None,
    q: str | None = Query(None, max_length=200),
    db: Session = Depends(get_db),
):
    """Identity, account state, groups (direct and nested, with their path), the folders reached and how."""
    if storage_root_id is not None:
        require_storage_root_access(db, actor_from_request(request), int(storage_root_id))
    explorer = _explorer(request, db)
    return ui_data(_found(explorer.user(user_id, offset=offset, limit=limit, include_broad=include_broad, root_id=storage_root_id, q=q)))


@router.get("/groups/{group_id}")
def group_access(
    group_id: int,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: str | None = Query(None, max_length=200),
    db: Session = Depends(get_db),
):
    """Members, nested groups, groups holding it, the folders it reaches (itself or through them), its exposure."""
    return ui_data(_found(_explorer(request, db).group(group_id, offset=offset, limit=limit, q=q)))
