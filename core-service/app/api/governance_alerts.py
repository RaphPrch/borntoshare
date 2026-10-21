from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.data.repositories.governance_alerts_repo import (
    ACKNOWLEDGED_STATUS,
    RESOLVED_STATUS,
    GovernanceAlertsRepo,
)
from app.api._helpers import ui_action, ui_list
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, can_access_admin

router = APIRouter(prefix="/governance-alerts", tags=["governance_alerts"])


@router.get("")
def list_governance_alerts(
    scope_type: str | None = None,
    scope_id: int | None = None,
    storage_root_id: int | None = None,
    storage_endpoint_id: int | None = None,
    status: str = "open",
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    repo = GovernanceAlertsRepo(db)
    rows = repo.list_alerts(
        scope_type=scope_type,
        scope_id=scope_id,
        storage_root_id=storage_root_id,
        storage_endpoint_id=storage_endpoint_id,
        status=status,
        limit=limit,
    )
    return ui_list(
        rows,
        meta={
            "scope_type": scope_type,
            "scope_id": int(scope_id) if scope_id is not None else None,
            "storage_root_id": int(storage_root_id) if storage_root_id is not None else None,
            "storage_endpoint_id": int(storage_endpoint_id) if storage_endpoint_id is not None else None,
            "status": status,
            "limit": int(limit),
            "count": int(len(rows)),
        },
    )


@router.get("/storage-roots/{storage_root_id}")
def list_storage_root_alerts(
    storage_root_id: int,
    status: str = "open",
    reconcile: bool = True,
    db: Session = Depends(get_db),
):
    repo = GovernanceAlertsRepo(db)
    rows = (
        repo.reconcile_storage_root(int(storage_root_id), commit=True)
        if reconcile and str(status or "open").lower() == "open"
        else repo.list_for_storage_root(int(storage_root_id), status=status)
    )
    return ui_list(
        rows,
        meta={"storage_root_id": int(storage_root_id), "status": status, "count": int(len(rows))},
    )



def _change_alert_status(alert_id: int, new_status: str, action: str, request: Request, db: Session):
    repo = GovernanceAlertsRepo(db)
    alert = repo.get_alert(int(alert_id))
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    actor = actor_from_request(request)
    if not can_access_admin(actor):
        raise HTTPException(status_code=403, detail="Platform administrator required")
    repo.set_status(int(alert_id), new_status, actor_id=actor.identity_id)
    log_activity(
        db,
        actor_type="user" if actor.identity_id is not None else "system",
        actor_id=actor.identity_id,
        actor_display=actor.display_name,
        action=action,
        outcome="success",
        target_type="governance_alert",
        target_id=int(alert_id),
        target_display=str(alert.get("title") or alert.get("alert_type") or alert_id),
        context_json={"alert_type": alert.get("alert_type"), "severity": alert.get("severity"), "previous_status": alert.get("status")},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(ok=True, message=f"Alert {new_status}", action_id=int(alert_id), details={"status": new_status})


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, request: Request, db: Session = Depends(get_db)):
    return _change_alert_status(alert_id, ACKNOWLEDGED_STATUS, "governance_alert.acknowledged", request, db)


@router.post("/{alert_id}/resolve")
def resolve_alert(alert_id: int, request: Request, db: Session = Depends(get_db)):
    return _change_alert_status(alert_id, RESOLVED_STATUS, "governance_alert.resolved", request, db)
