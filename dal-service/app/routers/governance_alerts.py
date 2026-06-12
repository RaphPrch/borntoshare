from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.repositories.governance_alerts_repo import GovernanceAlertsRepo
from app.routers._helpers import ui_action, ui_list

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


@router.post("/reconcile/storage-roots/{storage_root_id}")
def reconcile_storage_root_alerts(
    storage_root_id: int,
    db: Session = Depends(get_db),
):
    repo = GovernanceAlertsRepo(db)
    rows = repo.reconcile_storage_root(int(storage_root_id), commit=True)
    return ui_action(
        ok=True,
        action_id=int(storage_root_id),
        message="governance_alerts.storage_root_reconciled",
        details={"alerts_count": int(len(rows))},
    )


@router.post("/reconcile/storage-roots")
def reconcile_all_storage_root_alerts(
    db: Session = Depends(get_db),
):
    repo = GovernanceAlertsRepo(db)
    count = repo.reconcile_all_storage_roots(commit=True)
    return ui_action(
        ok=True,
        action_id="storage_roots",
        message="governance_alerts.storage_roots_reconciled",
        details={"storage_roots_count": int(count)},
    )
