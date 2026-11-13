"""Dashboard endpoints consumed by frontend BFF.

Wizard-UI is the schema authority for dashboard views.
Exposes a minimal, SQL-first API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.data.repositories import lookups_repo
from app.core.db import get_db
from app.data.repositories.access_requests_views_repo import AccessRequestsViewsRepo
from app.data.repositories.dashboard_views_repo import DashboardViewsRepo
from app.api._helpers import ui_data
from app.services.authorization import (
    actor_from_request,
    filter_access_request_rows,
    get_guardian_storage_root_ids,
    require_admin,
)


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _is_failed(row: dict) -> bool:
    return str(row.get("latest_execution_status") or "").strip().upper() in {"FAILED", "ERROR", "TIMED_OUT"}


def _ends_soon(row: dict, now: datetime) -> bool:
    end = row.get("expires_at")
    if isinstance(end, str):
        try:
            end = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            return False
    if not isinstance(end, datetime):
        return False
    if end.tzinfo is not None:
        end = end.astimezone(timezone.utc).replace(tzinfo=None)
    return now <= end <= now + timedelta(days=30)


def _status(row: dict) -> str:
    return str(row.get("status") or "").strip().lower()


def _card(row: dict) -> dict:
    keys = (
        "request_id", "request_code", "status", "status_label", "storage_root_id", "storage_root_name", "target_path",
        "permission", "expires_at", "created_at", "updated_at", "requested_for_display", "latest_execution_status", "overdue",
    )
    return {key: row.get(key) for key in keys}


@router.get("/me")
def get_user_dashboard_me(
    request: Request,
    db: Session = Depends(get_db),
):
    """Dashboard of a user who is not an administrator; a guardian also gets the requests on their folders."""
    actor = actor_from_request(request)
    guardian_root_ids = set(get_guardian_storage_root_ids(db, actor)) if actor.identity_id is not None else set()
    rows = (
        filter_access_request_rows(
            db, actor, AccessRequestsViewsRepo(db).list(status=None, my_action=False, overdue_only=False, high_impact=False, q=None)
        )
        if actor.identity_id is not None
        else []
    )
    now = datetime.utcnow()
    mine = [row for row in rows if int(row.get("requester_identity_id") or 0) == actor.identity_id]
    guarded = [row for row in rows if int(row.get("storage_root_id") or 0) in guardian_root_ids]
    recent = now - timedelta(days=30)

    def _recent(row: dict) -> bool:
        stamp = row.get("updated_at") or row.get("created_at")
        return isinstance(stamp, datetime) and stamp.replace(tzinfo=None) >= recent

    payload: dict = {
        "role": "guardian" if guardian_root_ids else "user",
        "mine": {
            "pending": sum(1 for row in mine if _status(row) == "pending"),
            "active": sum(1 for row in mine if _status(row) == "approved"),
            "ending_30d": sum(1 for row in mine if _status(row) == "approved" and _ends_soon(row, now)),
            "failed": sum(1 for row in mine if _status(row) in {"pending", "approved"} and _is_failed(row)),
            "refused_30d": sum(1 for row in mine if _status(row) == "rejected" and _recent(row)),
        },
        "my_requests": [_card(row) for row in sorted(mine, key=lambda r: str(r.get("created_at") or ""), reverse=True)[:8]],
        "my_ending": [_card(row) for row in mine if _status(row) == "approved" and _ends_soon(row, now)][:8],
    }
    if guardian_root_ids:
        alerts = lookups_repo.folders_with_open_alerts(db, sorted(guardian_root_ids))
        to_decide = [row for row in guarded if _status(row) == "pending"]
        payload["guardian"] = {
            "folders": len(guardian_root_ids),
            "folders_with_alerts": int(alerts or 0),
            "to_decide": len(to_decide),
            "overdue": sum(1 for row in to_decide if row.get("overdue")),
            "failed": sum(1 for row in guarded if _status(row) in {"pending", "approved"} and _is_failed(row)),
            "active": sum(1 for row in guarded if _status(row) == "approved"),
            "ending_30d": sum(1 for row in guarded if _status(row) == "approved" and _ends_soon(row, now)),
            # Decisions of the last 30 days on the guarded folders
            "approved_30d": sum(1 for row in guarded if _status(row) in {"approved", "applied", "executed", "expired", "revoked"} and _recent(row)),
            "refused_30d": sum(1 for row in guarded if _status(row) == "rejected" and _recent(row)),
            "revoked_30d": sum(1 for row in guarded if _status(row) == "revoked" and _recent(row)),
        }
        payload["to_decide"] = [_card(row) for row in sorted(to_decide, key=lambda r: str(r.get("created_at") or ""))[:8]]
        payload["guarded_failed"] = [_card(row) for row in guarded if _status(row) in {"pending", "approved"} and _is_failed(row)][:8]
    return ui_data(payload)


@router.get("/platform-overview")
def get_platform_overview(request: Request, db: Session = Depends(get_db)):
    """Platform overview KPI (admin).

    Backed by Wizard view:
      - v_dashboard_overview
    """

    require_admin(actor_from_request(request))
    payload = DashboardViewsRepo(db).get_platform_overview()

    return ui_data(payload)

