from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api._helpers import ui_data, ui_list
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request
from app.services.identity_orchestration_service import (
    discover_identity as discover_identity_service,
    get_identity_job as get_identity_job_service,
    import_identity_ad as import_identity_ad_service,
    import_identity_ad_batch as import_identity_ad_batch_service,
    list_identity_overview as list_identity_overview_service,
    run_identity_snapshot as run_identity_snapshot_service,
    search_identity as search_identity_service,
    update_identity as update_identity_service,
)


router = APIRouter(prefix="/identity", tags=["identity-orchestration"])


@router.post("/snapshots/run")
async def run_identity_snapshot(request: Request) -> dict[str, Any]:
    incoming = await request.json()
    data = await run_identity_snapshot_service(incoming, request.headers.get("x-request-id") or None)
    actor = actor_from_request(request)
    log_activity(
        None,
        actor_type="user" if actor.identity_id is not None else "system",
        actor_id=actor.identity_id,
        actor_display=actor.display_name,
        action="identity_source.sync_requested",
        outcome="success",
        target_type="identity_source",
        target_id=int(incoming.get("identity_source_id") or 0) or None,
        context_json={"job_id": data.get("job_id"), "snapshot_id": data.get("snapshot_id"), "mode": incoming.get("mode")},
        correlation_id=str(data.get("correlation_id") or "") or None,
    )
    return ui_data(data)


@router.post("/search")
async def search_identity(request: Request) -> dict[str, Any]:
    incoming = await request.json()
    data = await search_identity_service(incoming)
    return ui_data(data)


@router.get("")
async def list_identity_overview(request: Request) -> dict[str, Any]:
    items = await list_identity_overview_service(dict(request.query_params))
    return ui_list(items)


@router.patch("/{identity_id}")
async def update_identity(identity_id: int, request: Request) -> dict[str, Any]:
    payload = await request.json()
    data = await update_identity_service(identity_id, payload, request)
    return ui_data(data)


@router.post("/import/ad")
async def import_identity_ad(request: Request) -> dict[str, Any]:
    incoming = await request.json()
    data = await import_identity_ad_service(incoming)
    return ui_data(data)


@router.post("/import/ad/batch")
async def import_identity_ad_batch(request: Request) -> dict[str, Any]:
    incoming = await request.json()
    data = await import_identity_ad_batch_service(incoming)
    return ui_data(data)


@router.post("/discover")
async def discover_identity(request: Request) -> dict[str, Any]:
    incoming = await request.json()
    data = await discover_identity_service(incoming, request.headers.get("x-request-id") or None)
    return ui_data(data)


@router.get("/jobs/{job_id}")
async def get_identity_job(job_id: int) -> dict[str, Any]:
    data = await get_identity_job_service(job_id)
    return ui_data(data)
