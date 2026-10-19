from __future__ import annotations

"""Dashboard endpoints consumed by frontend BFF.

Wizard-UI is the schema authority for dashboard views.
Exposes a minimal, SQL-first API.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

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


@router.get("/platform-overview")
def get_platform_overview(request: Request, db: Session = Depends(get_db)):
    """Platform overview KPI (admin).

    Backed by Wizard view:
      - v_dashboard_overview
    """

    require_admin(actor_from_request(request))
    payload = DashboardViewsRepo(db).get_platform_overview()

    return ui_data(payload)

