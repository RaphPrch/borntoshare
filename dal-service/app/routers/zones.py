from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.db import get_db
from app.routers._helpers import ui_action, ui_data, ui_list
from app.schemas.zone import ZoneCreate, ZoneUpdate
from app.repositories.zones_views_repo import ZonesViewsRepo
from app.services.activity_log import log_activity
from app.services.access_profiles_v1 import SYSTEM_MANAGED_ERROR

router = APIRouter(prefix="/zones", tags=["zones"])


def _clean_text(value: Any) -> str | None:
    raw = str(value or "").strip()
    return raw or None


def _get_zone_write_row(db: Session, zone_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT
              id,
              name,
              code,
              description
            FROM zones
            WHERE id = :id
            LIMIT 1
            """
        ),
        {"id": int(zone_id)},
    ).mappings().first()
    return dict(row) if row else None


def _validate_zone_policy_payload(*, payload: dict[str, Any]) -> dict[str, Any]:
    enabled = 1 if bool(payload.get("enabled")) else 0
    policy_mode = str(payload.get("policy_mode") or "ON_FIRST_ACCESS_REQUEST").strip().upper()
    ou_strategy = str(payload.get("ou_strategy") or "IDENTITY_DEFAULT").strip().upper()
    base_ou_dn = _clean_text(payload.get("base_ou_dn"))
    static_ou_dn = _clean_text(payload.get("static_ou_dn"))

    if policy_mode in {"INHERIT", "MANUAL", "ON_STORAGE_ROOT_CREATE"}:
        policy_mode = "ON_FIRST_ACCESS_REQUEST"
    if policy_mode != "ON_FIRST_ACCESS_REQUEST":
        raise HTTPException(status_code=422, detail="policy_mode must be ON_FIRST_ACCESS_REQUEST")
    if ou_strategy not in {"IDENTITY_DEFAULT", "ZONE_STATIC"}:
        raise HTTPException(status_code=422, detail="ou_strategy must be IDENTITY_DEFAULT or ZONE_STATIC")
    if ou_strategy == "ZONE_STATIC" and not static_ou_dn:
        raise HTTPException(status_code=422, detail="static_ou_dn required for ZONE_STATIC")

    return {
        "enabled": enabled,
        "policy_mode": policy_mode,
        "ou_strategy": ou_strategy,
        "base_ou_dn": base_ou_dn,
        "static_ou_dn": static_ou_dn,
    }


def _build_zone_policy_candidate(
    *,
    db: Session,
    zone_id: int,
    candidate_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    zone = ZonesViewsRepo(db).get(zone_id)
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    current_row = ZonesViewsRepo(db).get_zone_provisioning_policy(zone_id)

    base = {
        "enabled": bool((current_row or {}).get("enabled") or False),
        "policy_mode": str((current_row or {}).get("policy_mode") or "ON_FIRST_ACCESS_REQUEST"),
        "ou_strategy": str((current_row or {}).get("ou_strategy") or "IDENTITY_DEFAULT"),
        "base_ou_dn": (current_row or {}).get("base_ou_dn"),
        "static_ou_dn": (current_row or {}).get("static_ou_dn"),
    }

    incoming = dict(candidate_payload or {})
    merged = dict(base)
    for key in ("enabled", "policy_mode", "ou_strategy", "base_ou_dn", "static_ou_dn"):
        if key in incoming:
            merged[key] = incoming.get(key)

    return _validate_zone_policy_payload(payload=merged)


# ============================================================
# READ MODELS (VIEWS)
# ============================================================

@router.get("")
def list_zones(db: Session = Depends(get_db)):
    """
    List zones (READ MODEL).

    Backed by SQL view:
    - v_zones
    """
    rows = ZonesViewsRepo(db).list()
    return ui_list([dict(r) for r in rows])


@router.get("/{zone_id}/overview")
def get_zone_overview(zone_id: int, db: Session = Depends(get_db)):
    """
    Zone overview (READ MODEL).

    Backed by SQL view:
    - v_zones
    """
    row = ZonesViewsRepo(db).get(zone_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found",
        )
    return ui_data(dict(row), meta={"zone_id": int(zone_id)})




@router.get("/{zone_id}/console")
def get_zone_console(zone_id: int, db: Session = Depends(get_db)):
    """Ultra Gold console read-model for a zone (V1++).

    Legacy note:
    - access_profiles were removed from the active frontend console
    - this payload now focuses on zone, endpoints, roots and provisioning policy
    """

    repo = ZonesViewsRepo(db)
    zone = repo.get(zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found",
        )

    endpoints = repo.list_console_endpoints(zone_id)
    roots = repo.list_console_roots(zone_id)
    policy = repo.get_effective_provisioning_policy(zone_id)

    policy_payload = dict(policy) if policy else {
        "zone_id": zone_id,
        "enabled": 0,
        "ou_strategy": "IDENTITY_DEFAULT",
        "base_ou_dn": None,
        "static_ou_dn": None,
        "updated_at": None,
    }

    payload = {
        "zone": zone,
        "endpoints": [dict(r) for r in endpoints],
        "storage_roots": [dict(r) for r in roots],
        "provisioning_policy": policy_payload,
        "operational_summary": str((zone or {}).get("operational_summary") or "attention"),
        "kpis": {
            "endpoints_count": int(len(endpoints)),
            "storage_roots_count": int(len(roots)),
        },
    }
    return ui_data(payload, meta={"zone_id": int(zone_id)})


@router.get("/{zone_id}/provisioning-policy")
def get_zone_provisioning_policy(zone_id: int, db: Session = Depends(get_db)):
    row = ZonesViewsRepo(db).get_zone_provisioning_policy(zone_id)
    if row is None:
        # zone existence check
        zone = ZonesViewsRepo(db).get(zone_id)
        if not zone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
        row = {
            "zone_id": int(zone_id),
            "enabled": 0,
            "policy_mode": "ON_FIRST_ACCESS_REQUEST",
            "ou_strategy": "IDENTITY_DEFAULT",
            "base_ou_dn": None,
            "static_ou_dn": None,
            "updated_at": None,
        }

    return ui_data(dict(row), meta={"zone_id": int(zone_id)})


@router.get("/{zone_id}/provisioning-drift")
def get_zone_provisioning_drift(zone_id: int, db: Session = Depends(get_db)):
    _ = zone_id
    _ = db
    return ui_data(
        {
            "zone_id": int(zone_id),
            "drift_detected": False,
            "items": [],
        },
        meta={"zone_id": int(zone_id), "count": 0},
    )


@router.put("/{zone_id}/provisioning-policy")
def put_zone_provisioning_policy(zone_id: int, payload: dict, db: Session = Depends(get_db)):
    if "naming_template" in (payload or {}):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="naming_template is not part of zone provisioning-policy; use /zones/{zone_id}/naming-policies",
        )

    normalized = _build_zone_policy_candidate(
        db=db,
        zone_id=int(zone_id),
        candidate_payload=payload,
    )

    # upsert
    db.execute(
        text(
            """
            INSERT INTO zone_provisioning_policy
              (zone_id, enabled, policy_mode, ou_strategy, base_ou_dn, static_ou_dn)
            VALUES
              (:zone_id, :enabled, :policy_mode, :ou_strategy, :base_ou_dn, :static_ou_dn)
            ON DUPLICATE KEY UPDATE
              enabled = VALUES(enabled),
              policy_mode = VALUES(policy_mode),
              ou_strategy = VALUES(ou_strategy),
              base_ou_dn = VALUES(base_ou_dn),
              static_ou_dn = VALUES(static_ou_dn)
            """
        ),
        {
            "zone_id": zone_id,
            "enabled": int(normalized.get("enabled") or 0),
            "policy_mode": str(normalized.get("policy_mode") or "ON_FIRST_ACCESS_REQUEST"),
            "ou_strategy": str(normalized.get("ou_strategy") or "IDENTITY_DEFAULT"),
            "base_ou_dn": normalized.get("base_ou_dn"),
            "static_ou_dn": normalized.get("static_ou_dn"),
        },
    )
    db.commit()
    return get_zone_provisioning_policy(zone_id, db)


@router.get("/{zone_id}/access-profiles")
def list_zone_access_profiles(zone_id: int, db: Session = Depends(get_db)):
    """Legacy compatibility endpoint for access-profile bindings by zone."""
    zone = ZonesViewsRepo(db).get(zone_id)
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    return ui_data(
        {
            "zone_id": int(zone_id),
            "access_profiles": [],
            "count": 0,
        },
        meta={"zone_id": int(zone_id), "count": 0, "deprecated": True},
    )


@router.post("/{zone_id}/access-profiles/{profile_id}", status_code=status.HTTP_201_CREATED)
def attach_zone_access_profile(zone_id: int, profile_id: int, db: Session = Depends(get_db)):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SYSTEM_MANAGED_ERROR)


@router.delete("/{zone_id}/access-profiles/{profile_id}")
def detach_zone_access_profile(zone_id: int, profile_id: int, db: Session = Depends(get_db)):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SYSTEM_MANAGED_ERROR)
@router.get("/{zone_id}")
def get_zone(zone_id: int, db: Session = Depends(get_db)):
    """
    Zone write-model detail.

    Returns mutable zone fields from write model.
    """
    z = _get_zone_write_row(db, int(zone_id))
    if not z:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found",
        )

    return ui_data(
        {
            "id": int(z.get("id") or 0),
            "name": z.get("name"),
            "code": z.get("code"),
            "description": z.get("description"),
        },
        meta={"zone_id": int(z.get("id") or 0)},
    )


# ============================================================
# WRITE MODEL (CRUD)
# ============================================================

@router.post("", status_code=status.HTTP_201_CREATED)
def create_zone(payload: ZoneCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()

    result = db.execute(
        text(
            """
            INSERT INTO zones (name, code, description)
            VALUES (:name, :code, :description)
            """
        ),
        {
            "name": data.get("name"),
            "code": data.get("code"),
            "description": data.get("description"),
        },
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid zone data",
        )

    zone_id = int(getattr(result, "lastrowid", 0) or 0)
    if zone_id <= 0:
        zone_id = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar() or 0)

    # Activity (same transaction)
    log_activity(
        db,
        actor_type="system",
        actor_id=None,
        actor_display=None,
        action="zone.created",
        outcome="success",
        target_type="zone",
        target_id=int(zone_id),
        target_display=str(data.get("name") or ""),
        context_json={
            "zone": {
                "id": int(zone_id),
                "name": data.get("name"),
                "code": data.get("code"),
            }
        },
    )
    db.commit()

    return ui_action(action_id=int(zone_id), message="zone.created")


@router.patch("/{zone_id}")
def update_zone(zone_id: int, payload: ZoneUpdate, db: Session = Depends(get_db)):
    z = _get_zone_write_row(db, int(zone_id))
    if not z:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found",
        )

    before = {
        "name": z.get("name"),
        "code": z.get("code"),
        "description": z.get("description"),
    }
    requested = payload.model_dump(exclude_unset=True)

    allowed_fields = {"name", "code", "description"}
    data = {k: v for k, v in requested.items() if k in allowed_fields}
    if data:
        set_clause = ", ".join(f"{field} = :{field}" for field in data.keys())
        params = dict(data)
        params["id"] = int(zone_id)
        db.execute(text(f"UPDATE zones SET {set_clause} WHERE id = :id"), params)

    after = {
        "name": data.get("name", before.get("name")),
        "code": data.get("code", before.get("code")),
        "description": data.get("description", before.get("description")),
    }

    # Activity
    log_activity(
        db,
        actor_type="system",
        actor_id=None,
        actor_display=None,
        action="zone.updated",
        outcome="success",
        target_type="zone",
        target_id=int(zone_id),
        target_display=str(after.get("name") or before.get("name") or ""),
        context_json={"before": before, "after": after, "updated_fields": sorted(list(data.keys()))},
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid zone data",
        )

    return ui_action(action_id=int(zone_id), message="zone.updated")


@router.delete("/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db)):
    z = _get_zone_write_row(db, int(zone_id))
    if not z:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found",
        )

    attached_endpoints = int(
        db.execute(
            text(
                """
                SELECT COUNT(1)
                FROM storage_endpoints
                WHERE zone_id = :zone_id
                """
            ),
            {"zone_id": int(zone_id)},
        ).scalar()
        or 0
    )
    if attached_endpoints > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Zone cannot be deleted while storage endpoints are still attached",
        )

    db.execute(
        text(
            """
            DELETE FROM zones
            WHERE id = :zone_id
            """
        ),
        {"zone_id": int(zone_id)},
    )

    # Activity (same transaction, capture display before commit)
    log_activity(
        db,
        actor_type="system",
        actor_id=None,
        actor_display=None,
        action="zone.deleted",
        outcome="success",
        target_type="zone",
        target_id=int(zone_id),
        target_display=str(z.get("name") or ""),
        context_json={
            "zone": {
                "id": int(zone_id),
                "name": z.get("name"),
                "code": z.get("code"),
            }
        },
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raw = str(getattr(exc, "orig", exc) or "").lower()
        if "zone_delete_blocked_endpoints" in raw:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Zone cannot be deleted while storage endpoints are still attached",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zone delete failed",
        )
    return ui_action(action_id=int(zone_id), message="zone.deleted")
