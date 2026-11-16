"""Apply the removals of an access review: each access decided « remove » that a request granted is revoked through
the usual path (AD group membership removed, request revoked, audited); an access that does not come from
BornToShare (an AD group or an entry set by hand) is marked « to handle by hand »."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api import access_reviews as access_reviews_routes
from app.api._helpers import ui_data
from app.api.governance.access_requests import _bulk_revoke
from app.core.direct_call import call_route
from app.core.values import unwrap_data
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request

router = APIRouter(prefix="/access-reviews", tags=["access-reviews"])


def _manual_reason(item: dict[str, Any]) -> str:
    groups = sorted({str(via.get("group")) for via in item.get("via") or [] if via.get("group") and via.get("kind") in ("ad_only", "outside", "group")})
    return ("Accès hors BornToShare : retirer la personne de " + ", ".join(groups[:3])) if groups else "Accès hors BornToShare : à retirer à la main"


@router.post("/{review_id}/apply")
async def apply_access_review(review_id: int, request: Request) -> dict[str, Any]:
    removals = unwrap_data(await call_route(access_reviews_routes.list_access_review_removals, review_id=review_id, request=request))
    revoked = manual = failed = 0
    for item in removals or []:
        if not item.get("request_ids"):
            await call_route(access_reviews_routes.record_access_review_outcome, item_id=int(item["id"]),
                             payload={"outcome": "manual", "detail": _manual_reason(item)})
            manual += 1
            continue
        result = unwrap_data(await _bulk_revoke(payload={"decision_comment": f"Revue des accès #{review_id}"},
                                                requested_ids=[int(value) for value in item["request_ids"]], request=request))
        problems = {str(key): value for key, value in dict((result or {}).get("failed_reasons") or {}).items()}
        if problems:
            failed += 1
            await call_route(access_reviews_routes.record_access_review_outcome, item_id=int(item["id"]),
                             payload={"outcome": "failed", "detail": "; ".join(str(value) for value in problems.values())[:500]})
        else:
            revoked += 1
            await call_route(access_reviews_routes.record_access_review_outcome, item_id=int(item["id"]), payload={"outcome": "revoked"})
    actor = actor_from_request(request)
    log_activity(None, actor_type="user" if actor.identity_id is not None else "system", actor_id=actor.identity_id, actor_display=actor.display_name,
                 action="access_review.applied", outcome="failure" if failed else "success", target_type="access_review", target_id=str(review_id),
                 target_display=f"#{review_id}", context_json={"revoked": revoked, "manual": manual, "failed": failed, "count": revoked + manual + failed},
                 correlation_id=request.headers.get("x-request-id") or None)
    return ui_data({"revoked": revoked, "manual": manual, "failed": failed})
