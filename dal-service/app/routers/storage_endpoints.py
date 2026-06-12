from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.internal_auth import require_internal_token
from app.models.identity_sources import IdentitySource
from app.models.storage_endpoint import StorageEndpoint
from app.models.storage_root import StorageRoot
from app.schemas.storage_endpoint import (
    StorageEndpointCreate,
    StorageEndpointUpdate,
)
from app.repositories.storage_endpoints_views_repo import (
    StorageEndpointsViewsRepo,
)
from app.routers._helpers import to_dicts, ui_action, ui_data, ui_list
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, require_admin
from app.services.probe_results import (
    ProbeResultService,
    coerce_probe_datetime,
    normalize_probe_status_value,
)
from app.services.storage_endpoint_provisioning import (
    build_storage_endpoint_provisioning_payload,
    normalize_storage_endpoint_provisioning_update,
)

router = APIRouter(
    prefix="/storage-endpoints",
    tags=["storage_endpoints"],
)


class StorageEndpointProbeResultPayload(BaseModel):
    last_probe_status: str = Field(..., max_length=32)
    last_probe_at: str | None = None
    last_probe_message: str | None = Field(default=None, max_length=512)
    last_probe_job_id: int | None = None
    source_type: str | None = Field(default=None, max_length=80)


def _actor_from_headers(request: Request) -> tuple[int | None, str | None]:
    actor = actor_from_request(request)
    return actor.identity_id, actor.display_name


def _require_platform_admin(request: Request) -> None:
    require_admin(actor_from_request(request))


def _resolve_zone_context(
    db: Session,
    *,
    endpoint_id_value: int | None = None,
    zone_id_value: int | None = None,
) -> dict[str, int | str | None]:
    fallback_zone_id = int(zone_id_value or 0) or None
    endpoint_id = int(endpoint_id_value or 0) or None

    if endpoint_id is not None:
        row = StorageEndpointsViewsRepo(db).get_overview(int(endpoint_id))
        if isinstance(row, dict):
            row_zone_id = int(row.get("zone_id") or 0) or fallback_zone_id
            row_zone_name = str(row.get("zone_name") or "").strip()

            if row_zone_name:
                return {"id": row_zone_id, "name": row_zone_name}
            if row_zone_id is not None:
                return {"id": int(row_zone_id), "name": f"Zone #{int(row_zone_id)}"}
            return {"id": None, "name": None}

    if fallback_zone_id is None:
        return {"id": None, "name": None}
    return {"id": int(fallback_zone_id), "name": f"Zone #{int(fallback_zone_id)}"}


def _sync_endpoint_lifecycle(data: dict) -> dict:
    """Keep `status` and `is_active` coherent for write payloads."""
    normalized = dict(data)
    has_status = "status" in normalized and normalized.get("status") is not None
    has_active = "is_active" in normalized and normalized.get("is_active") is not None

    if has_status and not has_active:
        status_value = str(normalized.get("status") or "").strip().lower()
        normalized["is_active"] = status_value not in {"inactive", "disabled", "error"}

    if has_active and not has_status:
        normalized["status"] = "active" if bool(normalized.get("is_active")) else "disabled"

    if "last_probe_status" in normalized:
        normalized["last_probe_status"] = _normalize_probe_status_value(normalized.get("last_probe_status"))

    return normalized


def _normalize_probe_status_value(value: object) -> str | None:
    return normalize_probe_status_value(value)


def _coerce_probe_datetime(value: object):
    return coerce_probe_datetime(value)


def _cascade_endpoint_probe_failure_to_roots(
    db: Session,
    *,
    endpoint_id: int,
    probe_at: datetime,
    probe_message: str,
) -> list[dict[str, object]]:
    return ProbeResultService(db)._cascade_endpoint_probe_failure_to_roots(
        endpoint_id=endpoint_id,
        probe_at=probe_at,
        probe_message=probe_message,
    )


def _cascade_endpoint_probe_success_to_roots(
    db: Session,
    *,
    endpoint_id: int,
    probe_at: datetime,
    probe_message: str,
) -> list[dict[str, object]]:
    return ProbeResultService(db)._cascade_endpoint_probe_success_to_roots(
        endpoint_id=endpoint_id,
        probe_at=probe_at,
        probe_message=probe_message,
    )


def _identity_source_kind(source: IdentitySource | None) -> str:
    if source is None:
        return ""
    return str(getattr(source, "type", "")).strip().upper()


def _is_ad_identity_source(source: IdentitySource | None) -> bool:
    return _identity_source_kind(source) in {"AD", "LDAP", "LDAPS"}


def _requires_ad_identity_source(*, endpoint_type: str | None, protocol: str | None) -> bool:
    normalized_type = str(endpoint_type or "").strip().lower()
    normalized_protocol = str(protocol or "").strip().lower()
    return normalized_type in {"smb", "cifs"} or normalized_protocol in {"smb", "cifs"}


def _validate_identity_source_for_endpoint(
    db: Session,
    *,
    identity_source_id: int | None,
    require_ad: bool,
) -> IdentitySource | None:
    source_id = int(identity_source_id or 0) or None
    if source_id is None:
        return None

    source = db.get(IdentitySource, int(source_id))
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "ENDPOINT_IDENTITY_SOURCE_NOT_FOUND",
                "message": "identity_source_id does not reference an existing identity source",
            },
        )

    if not bool(getattr(source, "is_active", True)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "ENDPOINT_IDENTITY_SOURCE_INACTIVE",
                "message": "identity_source_id points to an inactive identity source",
                "hint": "Enable the identity source or choose another active AD source",
            },
        )

    if require_ad and not _is_ad_identity_source(source):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "ENDPOINT_IDENTITY_SOURCE_INVALID_KIND",
                "message": "SMB endpoints require an AD/LDAP identity source",
            },
        )

    return source


def _enrich_probe_fields(row: dict) -> dict:
    enriched = dict(row)
    if "last_probe_status" not in enriched:
        enriched["last_probe_status"] = None

    if "last_probe_at" not in enriched:
        enriched["last_probe_at"] = None

    if "last_probe_message" not in enriched:
        enriched["last_probe_message"] = None

    if "last_probe_job_id" not in enriched:
        enriched["last_probe_job_id"] = None

    if "operational_state" not in enriched:
        is_active = enriched.get("is_active")
        last_probe_status = str(enriched.get("last_probe_status") or enriched.get("status") or "").strip().lower()
        if is_active is False:
            enriched["operational_state"] = "disabled"
        elif last_probe_status == "success":
            enriched["operational_state"] = "reachable"
        elif last_probe_status == "running":
            enriched["operational_state"] = "checking"
        elif last_probe_status == "failed":
            enriched["operational_state"] = "unreachable"
        else:
            enriched["operational_state"] = "unknown"

    if "roots_count" not in enriched:
        enriched["roots_count"] = None
    return enriched


# ============================================================
# READ MODELS (SQL VIEWS ONLY)
# ============================================================

@router.get(
    "",
    summary="Storage endpoints list (UI)",
)
def list_storage_endpoints(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    UI list of storage endpoints.

    Backed by SQL view:
      - v_storage_endpoints_context

    CONTRACT:
    - Returns: [ {...}, {...} ]
    - Flat list
    """
    _require_platform_admin(request)
    repo = StorageEndpointsViewsRepo(db)
    rows = repo.list_context()
    payload = [_enrich_probe_fields(item) for item in to_dicts(rows)]
    return ui_list(payload)


@router.get(
    "/context",
    summary="Storage endpoints context (wizard / governance)",
)
def list_storage_endpoints_context(
    request: Request,
    zone_id: int | None = None,
    endpoint_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Context list for wizard / governance.

    Backed by SQL view:
      - v_storage_endpoints_context
    """
    _require_platform_admin(request)
    repo = StorageEndpointsViewsRepo(db)
    rows = repo.list_context(
        zone_id=zone_id,
        endpoint_type=endpoint_type,
        status=status,
    )
    payload = [_enrich_probe_fields(item) for item in to_dicts(rows)]
    return ui_list(
        payload,
        meta={
            "zone_id": int(zone_id) if zone_id is not None else None,
            "endpoint_type": endpoint_type,
            "status": status,
            "count": int(len(payload)),
        },
    )


@router.get(
    "/{storage_endpoint_id}/overview",
    summary="Storage endpoint overview",
)
def storage_endpoint_overview(
    storage_endpoint_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Overview for a single storage endpoint.

    Backed by SQL view:
      - v_storage_endpoint_detail
    """
    _require_platform_admin(request)
    repo = StorageEndpointsViewsRepo(db)

    row = repo.get_overview(storage_endpoint_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage endpoint not found",
        )

    if not isinstance(row, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid storage endpoint overview format",
        )

    return ui_data(_enrich_probe_fields(row), meta={"storage_endpoint_id": int(storage_endpoint_id)})


@router.get(
    "/{endpoint_id}",
    summary="Get storage endpoint detail",
)
def get_storage_endpoint(
    endpoint_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_platform_admin(request)
    endpoint = db.get(StorageEndpoint, int(endpoint_id))
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage endpoint not found",
        )

    row = StorageEndpointsViewsRepo(db).get_overview(int(endpoint_id))
    payload = _enrich_probe_fields(dict(row)) if isinstance(row, dict) else {}

    payload.setdefault("id", int(getattr(endpoint, "id", 0) or 0))
    payload.setdefault("name", str(getattr(endpoint, "name", "") or ""))
    payload.setdefault("type", str(getattr(endpoint, "endpoint_type", "") or ""))
    payload.setdefault("protocol", getattr(endpoint, "protocol", None))
    payload.setdefault("host", getattr(endpoint, "host", None))
    payload.setdefault("port", getattr(endpoint, "port", None))
    payload.setdefault("zone_id", int(getattr(endpoint, "zone_id", 0) or 0) or None)
    payload.setdefault(
        "identity_source_id",
        int(getattr(endpoint, "identity_source_id", 0) or 0) or None,
    )
    endpoint_target = str(getattr(endpoint, "host", "") or "").strip()
    endpoint_port = int(getattr(endpoint, "port", 0) or 0)
    if endpoint_target and endpoint_port > 0:
        endpoint_target = f"{endpoint_target}:{endpoint_port}"
    payload.setdefault("endpoint_target", endpoint_target or None)
    payload.setdefault("config_json", None)

    return ui_data(payload, meta={"storage_endpoint_id": int(endpoint_id)})



@router.get(
    "/{storage_endpoint_id}/console",
    summary="Storage endpoint console (GOLD)",
)
def storage_endpoint_console(
    storage_endpoint_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Consolidated read-model for the Storage Endpoint admin page.

    Includes:
    - endpoint overview (v_storage_endpoint_detail)
    - attached storage roots (v_storage_roots_context filtered)
    - KPIs
    """
    _require_platform_admin(request)
    se_repo = StorageEndpointsViewsRepo(db)

    payload = se_repo.get_console(storage_endpoint_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage endpoint not found",
        )

    return ui_data(
        {
            "endpoint": _enrich_probe_fields(payload.get("endpoint") or {}),
            "storageRoots": payload.get("storageRoots") or [],
            "kpis": payload.get("kpis") or {"roots_count": 0},
        },
        meta={"storage_endpoint_id": int(storage_endpoint_id)},
    )


@router.get("/{endpoint_id}/provisioning-policy", summary="Storage endpoint provisioning policy")
def get_storage_endpoint_provisioning_policy(
    endpoint_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_platform_admin(request)
    endpoint = db.get(StorageEndpoint, int(endpoint_id))
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage endpoint not found")

    return ui_data(
        build_storage_endpoint_provisioning_payload(db=db, endpoint=endpoint),
        meta={"storage_endpoint_id": int(endpoint_id)},
    )


@router.put("/{endpoint_id}/provisioning-policy", summary="Update storage endpoint provisioning policy")
def put_storage_endpoint_provisioning_policy(
    endpoint_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_platform_admin(request)
    endpoint = db.get(StorageEndpoint, int(endpoint_id))
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage endpoint not found")

    normalized = normalize_storage_endpoint_provisioning_update(payload)

    if normalized.get("policy_mode") == "inherit":
        endpoint.sub_ou_dn = None
        endpoint.naming_template = None
    else:
        endpoint_values = normalized.get("endpoint_values") if isinstance(normalized.get("endpoint_values"), dict) else {}
        endpoint.sub_ou_dn = str(endpoint_values.get("ou_dn") or "").strip() or None
        endpoint.naming_template = str(endpoint_values.get("naming_template") or "").strip() or None

    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)

    return ui_data(
        build_storage_endpoint_provisioning_payload(db=db, endpoint=endpoint),
        meta={"storage_endpoint_id": int(endpoint_id)},
    )

# ============================================================
# WRITE MODEL (TABLE storage_endpoint)
# ============================================================

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create storage endpoint",
)
def create_endpoint(
    payload: StorageEndpointCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Create a storage endpoint (WRITE MODEL).
    """

    _require_platform_admin(request)
    data = _sync_endpoint_lifecycle(payload.model_dump())

    if data.get("bind_dn") and not data.get("bind_password_ref"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bind_password_ref is required when bind_dn is provided",
        )

    require_ad = _requires_ad_identity_source(
        endpoint_type=str(data.get("endpoint_type") or ""),
        protocol=str(data.get("protocol") or ""),
    )
    _validate_identity_source_for_endpoint(
        db,
        identity_source_id=int(data.get("identity_source_id") or 0) or None,
        require_ad=require_ad,
    )

    endpoint = StorageEndpoint(**data)

    db.add(endpoint)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storage endpoint conflict",
        )

    db.refresh(endpoint)
    zone_ctx = _resolve_zone_context(
        db,
        endpoint_id_value=int(endpoint.id),
        zone_id_value=int(getattr(endpoint, "zone_id", 0) or 0) or None,
    )

    initial_probe_status = str(getattr(endpoint, "last_probe_status", "") or "").strip().lower()
    if initial_probe_status:
        ProbeResultService(db).record_storage_endpoint_probe(
            endpoint,
            status_value=initial_probe_status,
            checked_at=_coerce_probe_datetime(getattr(endpoint, "last_probe_at", None)),
            message=(str(getattr(endpoint, "last_probe_message", "") or "").strip() or None),
            source_type="storage_endpoint_create",
            source_id=str(int(endpoint.id)),
            job_id=int(getattr(endpoint, "last_probe_job_id", 0) or 0) or None,
            correlation_id=(request.headers.get("x-request-id") or None),
            cascade_to_roots=False,
        )
        db.commit()

    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_endpoint.created",
        outcome="success",
        target_type="storage_endpoint",
        target_id=int(endpoint.id),
        target_display=str(endpoint.name or endpoint.host or endpoint.id),
        context_json={
            "name": endpoint.name,
            "host": endpoint.host,
            "protocol": endpoint.protocol,
            "zone": zone_ctx.get("name"),
            "zone_id": zone_ctx.get("id"),
            "zone_name": zone_ctx.get("name"),
            "is_active": bool(endpoint.is_active),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )

    return ui_action(action_id=int(endpoint.id), message="storage_endpoint.created")


@router.patch(
    "/{endpoint_id}",
    summary="Update storage endpoint",
)
def update_endpoint(
    endpoint_id: int,
    payload: StorageEndpointUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Partial update of a storage endpoint.
    """
    _require_platform_admin(request)
    endpoint = db.get(StorageEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage endpoint not found",
        )

    before = {
        "name": endpoint.name,
        "host": endpoint.host,
        "port": endpoint.port,
        "protocol": endpoint.protocol,
        "endpoint_type": endpoint.endpoint_type,
        "identity_source_id": int(getattr(endpoint, "identity_source_id", 0) or 0) or None,
        "zone_id": int(getattr(endpoint, "zone_id", 0) or 0) or None,
        "status": endpoint.status,
        "is_active": bool(endpoint.is_active),
    }
    critical_before = {
        **before,
        "bind_dn": endpoint.bind_dn,
        "bind_password_ref": endpoint.bind_password_ref,
    }
    before_zone_ctx = _resolve_zone_context(
        db,
        endpoint_id_value=int(endpoint.id),
        zone_id_value=int(before.get("zone_id") or 0) or None,
    )

    updates = _sync_endpoint_lifecycle(payload.model_dump(exclude_unset=True))

    next_bind_dn = updates.get("bind_dn", endpoint.bind_dn)
    next_bind_ref = updates.get("bind_password_ref", endpoint.bind_password_ref)
    if next_bind_dn and not next_bind_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bind_password_ref is required when bind_dn is provided",
        )

    next_endpoint_type = updates.get("endpoint_type", endpoint.endpoint_type)
    next_protocol = updates.get("protocol", endpoint.protocol)
    require_ad = _requires_ad_identity_source(
        endpoint_type=str(next_endpoint_type or ""),
        protocol=str(next_protocol or ""),
    )

    should_validate_identity_source = (
        "identity_source_id" in updates
        or "endpoint_type" in updates
        or "protocol" in updates
    )
    if should_validate_identity_source:
        _validate_identity_source_for_endpoint(
            db,
            identity_source_id=(
                int(updates.get("identity_source_id") or 0)
                if "identity_source_id" in updates
                else int(getattr(endpoint, "identity_source_id", 0) or 0)
            )
            or None,
            require_ad=require_ad,
        )

    for field, value in updates.items():
        setattr(endpoint, field, value)

    probe_status = str(updates.get("last_probe_status") or "").strip().lower()
    probe_failed_roots: list[dict[str, object]] = []
    if probe_status:
        probe_message = str(updates.get("last_probe_message") or "").strip() or None
        impacted_roots = ProbeResultService(db).record_storage_endpoint_probe(
            endpoint,
            status_value=probe_status,
            checked_at=_coerce_probe_datetime(updates.get("last_probe_at")),
            message=probe_message,
            source_type="storage_endpoint_update",
            source_id=str(int(endpoint.id)),
            job_id=int(updates.get("last_probe_job_id") or 0) or None,
            correlation_id=(request.headers.get("x-request-id") or None),
            cascade_to_roots=True,
        )
        if probe_status == "failed":
            probe_failed_roots = impacted_roots

    critical_fields = {
        "host",
        "port",
        "protocol",
        "endpoint_type",
        "identity_source_id",
        "bind_dn",
        "bind_password_ref",
    }
    changed_critical_fields = [
        field
        for field in sorted(critical_fields)
        if field in updates and critical_before.get(field) != getattr(endpoint, field, None)
    ]
    revalidation_roots: list[dict[str, object]] = []
    if changed_critical_fields and probe_status != "failed":
        revalidation_roots = ProbeResultService(db).mark_roots_need_revalidation(
            endpoint=endpoint,
            reason=f"storage_endpoint_configuration_changed:{','.join(changed_critical_fields)}",
            correlation_id=(request.headers.get("x-request-id") or None),
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storage endpoint conflict",
        )

    after = {
        "name": endpoint.name,
        "host": endpoint.host,
        "port": endpoint.port,
        "protocol": endpoint.protocol,
        "endpoint_type": endpoint.endpoint_type,
        "identity_source_id": int(getattr(endpoint, "identity_source_id", 0) or 0) or None,
        "zone_id": int(getattr(endpoint, "zone_id", 0) or 0) or None,
        "status": endpoint.status,
        "is_active": bool(endpoint.is_active),
    }
    after_zone_ctx = _resolve_zone_context(
        db,
        endpoint_id_value=int(endpoint.id),
        zone_id_value=int(after.get("zone_id") or 0) or None,
    )
    before["zone_name"] = before_zone_ctx.get("name")
    after["zone_name"] = after_zone_ctx.get("name")
    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_endpoint.updated",
        outcome="success",
        target_type="storage_endpoint",
        target_id=int(endpoint.id),
        target_display=str(endpoint.name or endpoint.host or endpoint.id),
        context_json={
            "before": before,
            "after": after,
            "zone": after_zone_ctx.get("name") or before_zone_ctx.get("name"),
            "zone_id": after_zone_ctx.get("id") or before_zone_ctx.get("id"),
            "zone_name": after_zone_ctx.get("name") or before_zone_ctx.get("name"),
            "updated_fields": sorted(list(updates.keys())),
            "revalidation_roots": len(revalidation_roots),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )

    if before.get("zone_id") != after.get("zone_id") and after.get("zone_id"):
        log_activity(
            db,
            actor_type="user" if actor_id is not None else "system",
            actor_id=actor_id,
            actor_display=actor_display,
            action="zone.storage_endpoint_added",
            outcome="success",
            target_type="zone",
            target_id=int(after.get("zone_id") or 0),
            target_display=str(after_zone_ctx.get("name") or f"Zone #{after.get('zone_id')}"),
            context_json={
                "message": "Storage endpoint added to zone",
                "storage_endpoint_id": int(endpoint.id),
                "storage_endpoint_name": str(endpoint.name or endpoint.host or endpoint.id),
                "zone_id": int(after.get("zone_id") or 0),
                "zone_name": after_zone_ctx.get("name"),
                "previous_zone_id": before.get("zone_id"),
                "previous_zone_name": before_zone_ctx.get("name"),
            },
            correlation_id=(request.headers.get("x-request-id") or None),
        )

    if probe_failed_roots:
        root_reason = str(updates.get("last_probe_message") or "").strip() or "Storage endpoint probe failed"
        for root in probe_failed_roots:
            root_id = int(root.get("id") or 0)
            if root_id <= 0:
                continue
            root_display = (
                str(root.get("name") or "").strip()
                or str(root.get("root_path") or "").strip()
                or f"Storage root #{root_id}"
            )
            log_activity(
                db,
                actor_type="user" if actor_id is not None else "system",
                actor_id=actor_id,
                actor_display=actor_display,
                action="storage_root.unavailable_from_endpoint_probe",
                outcome="failure",
                target_type="storage_root",
                target_id=int(root_id),
                target_display=root_display,
                context_json={
                    "storage_root_id": int(root_id),
                    "storage_root_name": root.get("name"),
                    "storage_root_path": root.get("root_path"),
                    "previous_probe_status": root.get("previous_probe_status"),
                    "probe_status": "failed",
                    "availability": "unavailable",
                    "health_badge": "warning",
                    "reason": root_reason,
                    "source_endpoint_id": int(endpoint.id),
                    "source_endpoint_name": endpoint.name,
                    "zone": after_zone_ctx.get("name") or before_zone_ctx.get("name"),
                    "zone_id": after_zone_ctx.get("id") or before_zone_ctx.get("id"),
                    "zone_name": after_zone_ctx.get("name") or before_zone_ctx.get("name"),
                },
                correlation_id=(request.headers.get("x-request-id") or None),
            )

    return ui_action(action_id=int(endpoint_id), message="storage_endpoint.updated")


@router.post("/{endpoint_id}/probe-result", dependencies=[Depends(require_internal_token)])
def record_storage_endpoint_probe_result(
    endpoint_id: int,
    payload: StorageEndpointProbeResultPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    endpoint = db.get(StorageEndpoint, int(endpoint_id))
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage endpoint not found",
        )

    normalized_status = _normalize_probe_status_value(payload.last_probe_status)
    if not normalized_status:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="last_probe_status is required",
        )

    checked_at = _coerce_probe_datetime(payload.last_probe_at)
    message = str(payload.last_probe_message or "").strip() or None
    impacted_roots = ProbeResultService(db).record_storage_endpoint_probe(
        endpoint,
        status_value=normalized_status,
        checked_at=checked_at,
        message=message,
        source_type=str(payload.source_type or "storage_endpoint_probe_result"),
        source_id=str(int(endpoint.id)),
        job_id=int(payload.last_probe_job_id or 0) or None,
        correlation_id=(request.headers.get("x-request-id") or None),
        cascade_to_roots=True,
    )

    actor_id, actor_display = _actor_from_headers(request)
    zone_ctx = _resolve_zone_context(
        db,
        endpoint_id_value=int(endpoint.id),
        zone_id_value=int(getattr(endpoint, "zone_id", 0) or 0) or None,
    )
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_endpoint.probe_result_recorded",
        outcome="success" if normalized_status == "success" else "failure",
        target_type="storage_endpoint",
        target_id=int(endpoint.id),
        target_display=str(endpoint.name or endpoint.host or endpoint.id),
        context_json={
            "probe_status": normalized_status,
            "probe_message": message,
            "host": endpoint.host,
            "protocol": endpoint.protocol,
            "zone_id": zone_ctx.get("id"),
            "zone_name": zone_ctx.get("name"),
            "impacted_roots": len(impacted_roots),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )

    db.commit()
    return ui_data(
        {
            "storage_endpoint_id": int(endpoint.id),
            "last_probe_status": normalized_status,
            "last_probe_at": checked_at.isoformat(),
            "last_probe_message": message,
            "impacted_roots": impacted_roots,
        },
        meta={"storage_endpoint_id": int(endpoint.id)},
    )


@router.delete(
    "/{endpoint_id}",
    summary="Delete storage endpoint",
)
def delete_endpoint(
    endpoint_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Delete a storage endpoint.

    Note:
    - Deleting an endpoint will also delete its storage roots
      (cascade = all, delete-orphan)
    """
    _require_platform_admin(request)
    endpoint = db.get(StorageEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage endpoint not found",
        )

    roots_linked = (
        db.query(StorageRoot.id)
        .filter(StorageRoot.storage_endpoint_id == int(endpoint_id))
        .limit(1)
        .first()
        is not None
    )
    if roots_linked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storage endpoint has declared storage roots and cannot be deleted",
        )

    target_display = str(endpoint.name or endpoint.host or endpoint.id)
    zone_ctx = _resolve_zone_context(
        db,
        endpoint_id_value=int(endpoint.id),
        zone_id_value=int(getattr(endpoint, "zone_id", 0) or 0) or None,
    )
    context = {
        "name": endpoint.name,
        "host": endpoint.host,
        "protocol": endpoint.protocol,
        "zone": zone_ctx.get("name"),
        "zone_id": zone_ctx.get("id"),
        "zone_name": zone_ctx.get("name"),
    }

    db.delete(endpoint)
    db.commit()

    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_endpoint.deleted",
        outcome="success",
        target_type="storage_endpoint",
        target_id=int(endpoint_id),
        target_display=target_display,
        context_json=context,
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(action_id=int(endpoint_id), message="storage_endpoint.deleted")
