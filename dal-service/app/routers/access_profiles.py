from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.routers._helpers import ui_data, ui_list
from app.services.access_profiles_v1 import SYSTEM_MANAGED_ERROR

router = APIRouter(prefix="/access-profiles", tags=["access-profiles"])
LEGACY_ACCESS_PROFILES_MESSAGE = (
    "The access_profiles read-model has been retired from the active application contract."
)


# ============================================================
# LIST (READ MODEL)
# Backed by: access_profiles
# ============================================================

@router.get("")
def list_profiles(db: Session = Depends(get_db)):
    """
    Legacy read-model endpoint for access profiles.

    Deprecated:
    - active frontend pages were removed
    - kept temporarily for compatibility while DAL / SQL cleanup is staged
    """
    _ = db
    return ui_list([], meta={"deprecated": True, "message": LEGACY_ACCESS_PROFILES_MESSAGE})


# ============================================================
# OVERVIEW (READ MODEL)
# Backed by: access_profiles (template only)
# ============================================================

@router.get("/{profile_id}")
def get_profile_overview(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """
    Legacy access-profile overview endpoint kept for compatibility only.
    """
    _ = db, profile_id
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_ACCESS_PROFILES_MESSAGE)




@router.get("/{profile_id}/console")
def get_access_profile_console(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """Legacy console read-model for a single access profile."""
    _ = db, profile_id
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_ACCESS_PROFILES_MESSAGE)
@router.get("/{profile_id}/members")
def list_profile_members(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """Legacy members read-model for a single access profile."""
    _ = db, profile_id
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_ACCESS_PROFILES_MESSAGE)


@router.get("/{profile_id}/activity")
def list_profile_activity(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """Legacy activity read-model for a single access profile."""
    _ = db, profile_id
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_ACCESS_PROFILES_MESSAGE)


# ============================================================
# CREATE (WRITE MODEL)
# ============================================================

@router.post("", status_code=status.HTTP_403_FORBIDDEN)
def create_profile():
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SYSTEM_MANAGED_ERROR)


# ============================================================
# UPDATE (WRITE MODEL)
# ============================================================

@router.put("/{profile_id}", status_code=status.HTTP_403_FORBIDDEN)
def update_profile(profile_id: int):
    _ = profile_id
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SYSTEM_MANAGED_ERROR)


@router.patch("/{profile_id}", status_code=status.HTTP_403_FORBIDDEN)
def patch_profile(profile_id: int):
    _ = profile_id
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SYSTEM_MANAGED_ERROR)


# ============================================================
# DELETE (WRITE MODEL)
# ============================================================

@router.delete("/{profile_id}", status_code=status.HTTP_403_FORBIDDEN)
def delete_profile(profile_id: int):
    _ = profile_id
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SYSTEM_MANAGED_ERROR)
