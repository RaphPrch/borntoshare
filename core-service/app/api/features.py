"""Features and licenses: what the license keys open, and what the administrators switched on.

- GET  /features                                   everyone signed in: the features usable now (the menu follows)
- POST /admin/advanced-settings/license            an administrator enters a license key (checked offline)
- DELETE /admin/advanced-settings/license/{id}     takes a license away (its features stop)
- PUT  /admin/advanced-settings/features/{key}     switches a licensed feature on or off
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import features
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, is_platform_administrator, require_admin

router = APIRouter(tags=["features"])


def _audit(db: Session, request: Request, action: str, target: str, context: dict) -> None:
    actor = actor_from_request(request)
    log_activity(db, actor_type="user" if actor.identity_id is not None else "system", actor_id=actor.identity_id,
                 actor_display=actor.display_name, action=action, outcome="success", target_type="feature", target_display=target,
                 context_json=context, correlation_id=(request.headers.get("x-request-id") or None))


@router.get("/features")
def list_features(request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    data = features.state(db)
    if not is_platform_administrator(actor):
        # The others only need to know what is usable (the menu); not the licenses
        return ui_data({"features": [{"key": f["key"], "label": f["label"], "enabled": f["enabled"]} for f in data["features"]]})
    return ui_data(data)


class LicensePayload(BaseModel):
    key: str = Field(min_length=20, max_length=2000)


@router.post("/admin/advanced-settings/license")
def add_license(payload: LicensePayload, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    try:
        lic = features.activate(db, payload.key, actor.display_name)
    except features.LicenseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"error_code": exc.code, "message": exc.message}) from exc
    _audit(db, request, "license.activated", lic.customer, {"license_id": lic.license_id, "features": list(lic.features),
                                                            "expires_on": lic.expires_on.isoformat() if lic.expires_on else None})
    return ui_data(features.state(db))


@router.delete("/admin/advanced-settings/license/{license_row_id}")
def delete_license(license_row_id: int, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    if not features.remove_license(db, license_row_id, actor.display_name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "LICENSE_NOT_FOUND", "message": "License not found"})
    _audit(db, request, "license.removed", str(license_row_id), {"license_row_id": license_row_id})
    return ui_data(features.state(db))


class SwitchPayload(BaseModel):
    enabled: bool


@router.put("/admin/advanced-settings/features/{feature}")
def switch_feature(feature: str, payload: SwitchPayload, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    current = next((item for item in features.state(db)["features"] if item["key"] == feature), None)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "FEATURE_UNKNOWN", "message": "Unknown feature"})
    if payload.enabled and not current["licensed"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "error_code": "FEATURE_NOT_LICENSED", "message": "No valid license opens this feature: enter a license key first"})
    features.switch(db, feature, payload.enabled, actor.display_name)
    _audit(db, request, "feature.enabled" if payload.enabled else "feature.disabled", current["label"], {"feature": feature})
    return ui_data(features.state(db))
