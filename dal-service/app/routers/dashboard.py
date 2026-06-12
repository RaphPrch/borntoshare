from __future__ import annotations

"""Dashboard endpoints consumed by frontend BFF.

Wizard-UI is the schema authority for dashboard views.
The DAL is responsible for exposing a minimal, SQL-first API.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.repositories.access_requests_views_repo import AccessRequestsViewsRepo
from app.repositories.dashboard_views_repo import DashboardViewsRepo
from app.routers._helpers import ui_data, ui_list
from app.services.authorization import (
    actor_from_request,
    filter_access_request_rows,
    get_guardian_storage_root_ids,
    is_platform_administrator,
    require_admin,
)


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _status_bucket(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"approved", "enforced"}:
        return "approved"
    if raw in {"rejected", "revoked", "closed"}:
        return "rejected_or_closed"
    return "open"


def _load_requester_ids(db: Session, request_ids: list[int]) -> dict[int, int]:
    ids = sorted({int(v) for v in (request_ids or []) if int(v) > 0})
    if not ids:
        return {}
    rows = (
        db.execute(
            text(
                """
                SELECT id AS request_id, requester_identity_id
                FROM access_requests
                WHERE id IN :ids
                """
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        )
        .mappings()
        .all()
    )
    out: dict[int, int] = {}
    for row in rows:
        request_id = int(row.get("request_id") or 0)
        requester_identity_id = int(row.get("requester_identity_id") or 0)
        if request_id > 0 and requester_identity_id > 0:
            out[request_id] = requester_identity_id
    return out


@router.get("/me")
def get_user_dashboard_me(
    request: Request,
    db: Session = Depends(get_db),
):
    actor = actor_from_request(request)
    if actor.identity_id is None:
        return ui_data(
            {
                "summary": {
                    "my_open_requests": 0,
                    "awaiting_my_review": 0,
                    "approved": 0,
                    "rejected_or_closed": 0,
                },
                "requires_action": [],
                "visible_requests": [],
            }
        )

    rows = AccessRequestsViewsRepo(db).list(status=None, my_action=False, overdue_only=False, high_impact=False, q=None)
    visible_rows = filter_access_request_rows(db, actor, rows)
    guardian_root_ids = set(get_guardian_storage_root_ids(db, actor))
    requester_ids_by_request = _load_requester_ids(
        db,
        [int(row.get("request_id") or 0) for row in visible_rows if int(row.get("request_id") or 0) > 0],
    )

    visible_requests: list[dict] = []
    requires_action: list[dict] = []
    summary = {
        "my_open_requests": 0,
        "awaiting_my_review": 0,
        "approved": 0,
        "rejected_or_closed": 0,
    }

    for row in visible_rows:
        payload = dict(row)
        request_id = int(payload.get("request_id") or 0)
        storage_root_id = int(payload.get("storage_root_id") or 0)
        requester_identity_id = requester_ids_by_request.get(request_id)
        is_requester = requester_identity_id == actor.identity_id
        is_guardian = storage_root_id > 0 and storage_root_id in guardian_root_ids
        viewer_role = "requester + guardian" if is_requester and is_guardian else "requester" if is_requester else "guardian" if is_guardian else "visible"
        bucket = _status_bucket(payload.get("status"))
        payload["viewer_role"] = viewer_role
        payload["is_requester"] = bool(is_requester)
        payload["is_guardian"] = bool(is_guardian)
        visible_requests.append(payload)

        if bucket == "approved":
            summary["approved"] += 1
        elif bucket == "rejected_or_closed":
            summary["rejected_or_closed"] += 1
        else:
            summary["my_open_requests"] += 1

        if is_guardian and bucket == "open":
            summary["awaiting_my_review"] += 1
            requires_action.append(payload)

    return ui_data(
        {
            "summary": summary,
            "requires_action": requires_action[:10],
            "visible_requests": visible_requests[:200],
        }
    )


@router.get("/summary")
def get_summary(
    request: Request,
    requester_identity_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Dashboard summary (global KPI).

    Backed by Wizard view:
      - v_dashboard_user_summary
    """

    actor = actor_from_request(request)
    effective_requester_identity_id = requester_identity_id if is_platform_administrator(actor) else actor.identity_id
    payload = DashboardViewsRepo(db).get_summary(requester_identity_id=effective_requester_identity_id)
    return ui_data(payload, meta={"requester_identity_id": effective_requester_identity_id})


@router.get("/latest-requests")
def list_latest_requests(
    request: Request,
    requester_identity_id: int | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    """Latest user requests.

    Backed by Wizard view:
      - v_dashboard_user_latest_requests
    """

    actor = actor_from_request(request)
    effective_requester_identity_id = requester_identity_id if is_platform_administrator(actor) else actor.identity_id
    lim = max(1, min(int(limit or 10), 100))
    payload = DashboardViewsRepo(db).list_latest_requests(
        requester_identity_id=effective_requester_identity_id,
        limit=lim,
    )
    return ui_list(
        payload,
        meta={
            "requester_identity_id": effective_requester_identity_id,
            "limit": lim,
            "count": int(len(payload)),
        },
    )


@router.get("/effective-access")
def list_effective_access(
    request: Request,
    requester_identity_id: int | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    """Effective access (user).

    Backed by Wizard view:
      - v_dashboard_user_effective_access
    """

    actor = actor_from_request(request)
    effective_requester_identity_id = requester_identity_id if is_platform_administrator(actor) else actor.identity_id
    lim = max(1, min(int(limit or 20), 200))
    payload = DashboardViewsRepo(db).list_effective_access(
        requester_identity_id=effective_requester_identity_id,
        limit=lim,
    )
    return ui_list(
        payload,
        meta={
            "requester_identity_id": effective_requester_identity_id,
            "limit": lim,
            "count": int(len(payload)),
        },
    )


@router.get("/platform-overview")
def get_platform_overview(request: Request, db: Session = Depends(get_db)):
    """Platform overview KPI (admin).

    Backed by Wizard view:
      - v_dashboard_overview
    """

    require_admin(actor_from_request(request))
    payload = DashboardViewsRepo(db).get_platform_overview()

    return ui_data(payload)


@router.get("/access-requests/expiring-soon")
def list_access_requests_expiring_soon(
    request: Request,
    requester_identity_id: int | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    """Expiring soon access requests.

    Backed by Wizard view:
      - v_access_requests_expiring_soon
    """

    actor = actor_from_request(request)
    effective_requester_identity_id = requester_identity_id if is_platform_administrator(actor) else actor.identity_id
    lim = max(1, min(int(limit or 200), 1000))
    payload = DashboardViewsRepo(db).list_access_requests_expiring_soon(
        requester_identity_id=effective_requester_identity_id,
        limit=lim,
    )
    return ui_list(
        payload,
        meta={
            "requester_identity_id": effective_requester_identity_id,
            "limit": lim,
            "count": int(len(payload)),
        },
    )
