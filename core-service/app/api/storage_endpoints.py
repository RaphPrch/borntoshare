from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.secret_store import forget_unused
from app.services.windows_names import dfs_folder_error, share_name_error
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.internal_auth import require_internal_token
from app.data.models.identity_sources import IdentitySource
from app.data.models.storage_endpoint import StorageEndpoint
from app.data.models.storage_root import StorageRoot
from app.schemas.storage_endpoint import (
    StorageEndpointCreate,
    StorageEndpointUpdate,
)
from app.data.repositories.storage_endpoints_views_repo import (
    StorageEndpointsViewsRepo,
)
from app.api._helpers import ui_action, ui_data, ui_list
from app.core.sql import to_dicts
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, admin_only, require_admin
from app.services.storage_guards import (
    endpoint_access_counts,
    endpoint_access_group_count,
    endpoint_root_count,
    normalize_root_path,
    rewrite_unc_host,
    same_host,
    unc_host,
)
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

def _assert_namespace_free(db: Session, path: str | None) -> None:
    from app.services.dfs_links import snapshot

    wanted = str(path or "").strip().rstrip("\\").lower()
    if not wanted.startswith("\\\\"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "DFS_NAMESPACE_PATH_INVALID", "message": "Read the namespace before adding it"},
        )
    for endpoint in db.query(StorageEndpoint).filter(StorageEndpoint.endpoint_type == "dfs").all():
        if str(snapshot(endpoint).get("path") or "").strip().rstrip("\\").lower() == wanted:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "DFS_NAMESPACE_TAKEN", "message": f"This namespace is already declared as {endpoint.name}"},
            )


def _resolved(host: str) -> set[str]:
    import socket

    try:
        return {info[4][0] for info in socket.getaddrinfo(host.strip(), None)}
    except (OSError, UnicodeError):
        return set()


def _assert_host_free(db: Session, host: str | None, *, exclude_id: int | None = None) -> None:
    """One file server, one endpoint: two would govern the same folders twice."""
    from app.services.storage_guards import same_host

    wanted = str(host or "").strip()
    if not wanted:
        return
    rows = db.execute(
        text("SELECT id, name, host FROM storage_endpoints WHERE host IS NOT NULL AND LOWER(endpoint_type) <> 'dfs'")
    ).mappings().all()
    taken = next((row for row in rows if row["id"] != exclude_id and same_host(str(row["host"]), wanted)), None)
    if taken is None:
        # The same server by its name and by its address (or two names): compared by what they resolve to
        wanted_ips = _resolved(wanted)
        taken = next(
            (row for row in rows if row["id"] != exclude_id and wanted_ips & _resolved(str(row["host"]))),
            None,
        ) if wanted_ips else None
    if taken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "STORAGE_ENDPOINT_HOST_TAKEN", "message": f"This file server is already declared as {taken['name']}"},
        )


class DfsSnapshotPayload(BaseModel):
    namespace: dict


class DfsManagePayload(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=500)


def _dfs_endpoint(db: Session, endpoint_id: int) -> StorageEndpoint:
    endpoint = db.get(StorageEndpoint, int(endpoint_id))
    if endpoint is None or str(endpoint.endpoint_type or "").lower() != "dfs":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DFS namespace not found")
    return endpoint


@router.get("/{endpoint_id}/dfs-links", summary="Folders of a DFS namespace and their targets")
def list_dfs_links(endpoint_id: int, request: Request, db: Session = Depends(get_db)):
    from app.services.dfs_links import describe_links, snapshot

    _require_platform_admin(request)
    endpoint = _dfs_endpoint(db, endpoint_id)
    shot = snapshot(endpoint)
    return ui_data({
        "path": shot.get("path"),
        "type": shot.get("type"),
        "root_targets": shot.get("root_targets") or [],
        "read_at": shot.get("read_at"),
        "error": shot.get("error"),
        "links": describe_links(db, endpoint),
        # The account was refused the management of the namespace (last try)
        "manage_denied": (endpoint.capabilities or {}).get("dfs_manage_denied") if isinstance(endpoint.capabilities, dict) else None,
        # The last change that went through, with the account that made it (valid while the account is the same)
        "manage_ok": (endpoint.capabilities or {}).get("dfs_manage_ok") if isinstance(endpoint.capabilities, dict) else None,
    })


@router.post("/{endpoint_id}/dfs-snapshot", summary="Keep the last reading of a DFS namespace")
def save_dfs_snapshot(endpoint_id: int, payload: DfsSnapshotPayload, request: Request, db: Session = Depends(get_db)):
    from app.services.dfs_links import snapshot

    _require_platform_admin(request)
    endpoint = _dfs_endpoint(db, endpoint_id)
    namespace = payload.namespace
    if str(namespace.get("path") or "").strip().lower() != str(snapshot(endpoint).get("path") or "").strip().lower():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DFS_NAMESPACE_MISMATCH", "message": "This reading is the one of another namespace"},
        )
    from app.services.dfs_links import store_snapshot

    links = store_snapshot(db, endpoint, namespace)
    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db, actor_type="user" if actor_id is not None else "system", actor_id=actor_id, actor_display=actor_display,
        action="storage_endpoint.dfs_read", outcome="success", target_type="storage_endpoint", target_id=int(endpoint.id),
        target_display=str(endpoint.name), context_json={"links": links, "path": namespace.get("path")},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_data({"links": links})


@router.post("/{endpoint_id}/dfs-links/manage", summary="Manage DFS folders: a storage root on each of their targets")
async def manage_dfs_links(endpoint_id: int, payload: DfsManagePayload, request: Request, db: Session = Depends(get_db)):
    from app.api.storage_roots import _create_storage_root, _queue_root_check, _refusal_text
    from app.schemas.storage_root import StorageRootCreate
    from app.services.dfs_links import describe_links

    _require_platform_admin(request)
    endpoint = _dfs_endpoint(db, endpoint_id)
    wanted = {str(path).strip().lower() for path in payload.paths}
    done: list[dict] = []
    failed: list[dict] = []
    for link in describe_links(db, endpoint):
        if str(link["path"]).lower() not in wanted:
            continue
        # Rights on every target or on none: a replica left out would refuse the users it serves
        if link["state"] in {"unknown_server", "no_target"}:
            failed.append({"path": link["path"], "message": "A target of this folder is on a file server that is not declared"})
            continue
        created: list[int] = []
        for target in link["targets"]:
            if target["storage_root_id"]:
                continue
            name = str(link["path"]).split("\\")[-1] or str(link["path"])
            try:
                root = _create_storage_root(
                    StorageRootCreate(
                        storage_endpoint_id=int(target["storage_endpoint_id"]),
                        name=name[:190],
                        root_path=str(target["root_path"]),
                        status="active",
                    ),
                    request,
                    db,
                    inherit_from_parent=True,
                )
                created.append(int(root.id))
                await _queue_root_check(int(root.id))
            except Exception as exc:
                db.rollback()
                failed.append({"path": link["path"], "target": target["unc"], "message": _refusal_text(exc)})
        done.append({"path": link["path"], "created": created})
    from app.services.dfs_links import forget_cache

    forget_cache()
    return ui_data({"managed": done, "failed": failed})


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
    if str(data.get("endpoint_type") or "").lower() == "dfs":
        # Several namespaces share their DFS server: one namespace is declared once
        _assert_namespace_free(db, ((data.get("capabilities") or {}).get("dfs_snapshot") or {}).get("path"))
    else:
        _assert_host_free(db, data.get("host"))

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
        # A DFS namespace is not a file server: its own line in the activity
        action="storage_endpoint.dfs_created" if str(endpoint.endpoint_type or "").lower() == "dfs" else "storage_endpoint.created",
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


def _guard_endpoint_change(db: Session, endpoint: Any, updates: dict[str, Any], *, rewrite_root_paths: bool) -> list[tuple[Any, str]]:
    """Refuse the changes that would leave the AD groups or the storage roots behind.

    - identity source or zone: the existing access groups stay in the other domain / OU
    - host: the storage roots keep \\\\old-host\\... in their path; rewritten only when asked
    Returns the (root, new path) to apply.
    """
    endpoint_id = int(endpoint.id)
    moved = [
        field for field in ("identity_source_id", "zone_id")
        if field in updates and (int(updates.get(field) or 0) or None) != (int(getattr(endpoint, field, 0) or 0) or None)
    ]
    if moved:
        groups = endpoint_access_group_count(db, endpoint_id)
        if groups:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "ENDPOINT_HAS_ACCESS_GROUPS",
                    "message": f"{groups} AD access group(s) already exist for the storage roots of this file server: "
                               "they would stay in the previous domain or OU",
                    "access_groups": groups,
                    "fields": moved,
                },
            )

    new_host = str(updates.get("host") or "").strip()
    if not new_host or same_host(new_host, endpoint.host):
        return []
    roots = db.query(StorageRoot).filter(StorageRoot.storage_endpoint_id == endpoint_id).all()
    if not roots:
        return []
    if not rewrite_root_paths:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ENDPOINT_HOST_HAS_ROOTS",
                "message": f"{len(roots)} storage root(s) use the current host in their path",
                "roots": len(roots),
                "old_host": endpoint.host,
                "new_host": new_host,
            },
        )
    rewrites = [(root, rewrite_unc_host(root.root_path, new_host)) for root in roots if unc_host(root.root_path)]
    for root, new_path in rewrites:
        clash = db.execute(
            text("SELECT id FROM storage_roots WHERE normalized_root_path = :path AND id <> :id LIMIT 1"),
            {"path": normalize_root_path(new_path), "id": int(root.id)},
        ).scalar()
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "STORAGE_ROOT_PATH_TAKEN", "message": f"{new_path} is already declared", "root_path": new_path},
            )
    return rewrites


@router.get("/{endpoint_id}/impact", summary="What depends on a storage endpoint")
def get_endpoint_impact(endpoint_id: int, request: Request, db: Session = Depends(get_db)):
    """Storage roots, AD access groups, active accesses and pending requests: shown before disabling or changing it."""
    _require_platform_admin(request)
    if db.get(StorageEndpoint, endpoint_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage endpoint not found")
    return ui_data(
        {
            "roots": endpoint_root_count(db, endpoint_id),
            "access_groups": endpoint_access_group_count(db, endpoint_id),
            **endpoint_access_counts(db, endpoint_id),
        }
    )


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
    if "host" in updates:
        _assert_host_free(db, updates.get("host"), exclude_id=int(endpoint.id))
    rewrite_root_paths = bool(updates.pop("rewrite_root_paths", False))
    root_path_rewrites = _guard_endpoint_change(db, endpoint, updates, rewrite_root_paths=rewrite_root_paths)

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

    host_moved = "host" in updates and not same_host(str(updates.get("host") or ""), endpoint.host)
    for field, value in updates.items():
        setattr(endpoint, field, value)
    if {"bind_dn", "bind_password_ref"} & set(updates):
        # Another account: its right to manage a DFS namespace is not known yet
        _remember_dfs_delegation(endpoint, denied=False)
    capabilities = endpoint.capabilities if isinstance(endpoint.capabilities, dict) else {}
    # Another account (or password) may hold the delegation: the refusal of the previous one no longer tells anything
    account_changed = "bind_dn" in updates or "bind_password_ref" in updates
    if account_changed and ("dfs_manage_denied" in capabilities or "dfs_manage_ok" in capabilities):
        capabilities = {key: value for key, value in capabilities.items() if key not in ("dfs_manage_denied", "dfs_manage_ok")}
        endpoint.capabilities = capabilities
    if host_moved and "discovered_roots_snapshot" in capabilities:
        # The shares found on the previous host carry its address: the next search lists them again
        endpoint.capabilities = {key: value for key, value in capabilities.items() if key != "discovered_roots_snapshot"}
    for root, new_path in root_path_rewrites:
        root.root_path = new_path
        root.normalized_root_path = normalize_root_path(new_path)

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


class ShareCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    # Local path on the file server; a folder under C:\\Shares when omitted
    path: str | None = Field(default=None, max_length=512)


_SHARE_REFUSALS = {
    "SHARE_ADMIN_REQUIRED": status.HTTP_403_FORBIDDEN,
    "SHARE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "SHARE_IN_USE": status.HTTP_409_CONFLICT,
    "SHARE_EXISTS": status.HTTP_409_CONFLICT,
    "SHARE_NAME_INVALID": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "SHARE_PATH_INVALID": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _share_endpoint(db: Session, endpoint_id: int) -> StorageEndpoint:
    endpoint = db.get(StorageEndpoint, int(endpoint_id))
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage endpoint not found")
    if not (endpoint.host and endpoint.bind_dn and endpoint.bind_password_ref):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "ENDPOINT_CREDENTIALS_MISSING", "message": "Le serveur de fichiers n'a ni hôte ni compte."})
    return endpoint


class _EndpointOperation:
    """A change made on a server by the worker (share, DFS folder), audited whatever the outcome."""

    def __init__(self, db: Session, request: Request, endpoint: StorageEndpoint, *, action: str, share: str, context: dict[str, Any]):
        self.db, self.request, self.endpoint = db, request, endpoint
        self.action, self.share, self.context = action, share, context
        self.actor = actor_from_request(request)

    def log(self, outcome: str, **extra: Any) -> None:
        log_activity(
            self.db,
            actor_type="user" if self.actor.identity_id is not None else "system",
            actor_id=self.actor.identity_id,
            actor_display=self.actor.display_name,
            action=self.action,
            outcome=outcome,
            target_type="storage_endpoint",
            target_id=int(self.endpoint.id),
            target_display=str(self.endpoint.name or self.endpoint.id),
            context_json={**self.context, **extra},
            correlation_id=(self.request.headers.get("x-request-id") or None),
        )

    def refused(self, http_status: int, code: str, message: str, job_id: int | None = None, **extra: Any) -> HTTPException:
        # The route writes its own refusal: no generic request.refused besides
        self.request.state.refusal_logged = True
        self.log("failure", reason=message, code=code)
        return HTTPException(status_code=http_status, detail={"code": code, "message": message, **extra, **({"job_id": job_id} if job_id else {})})

    async def run(self, protocol: str, path: str, *, failure_code: str, kind: str = "share",
                  target: dict[str, Any] | None = None) -> dict[str, Any]:
        import asyncio

        from app.services.probe_service import fetch_probe_job, submit_probe_run

        queued = await submit_probe_run({
            "kind": kind, "protocol": protocol, "scope": "write",
            "target": target or {"host": self.endpoint.host, "share": self.share, "path": path},
            "auth": {"mode": "ntlm", "username": self.endpoint.bind_dn, "secret_ref": self.endpoint.bind_password_ref},
            "options": {"timeout_sec": 60},
            "context": {"storage_endpoint_id": int(self.endpoint.id), "ui_origin": "admin"},
        })
        job_id = int((queued or {}).get("job_id") or 0)
        for _ in range(60):
            job = dict(await fetch_probe_job(job_id) or {})
            state = str(job.get("status") or "").lower()
            if state == "succeeded":
                return job
            if state in {"failed", "timed_out", "cancelled"}:
                error = job.get("error") if isinstance(job.get("error"), dict) else {}
                # A refusal is not a failure of the worker: retrying would give the same answer
                code = str(error.get("code") or failure_code)
                raise self.refused(_SHARE_REFUSALS.get(code, status.HTTP_502_BAD_GATEWAY), code, str(error.get("message") or state), job_id)
            await asyncio.sleep(1)
        raise self.refused(status.HTTP_504_GATEWAY_TIMEOUT, f"{failure_code.rsplit('_', 1)[0]}_TIMEOUT", "Le worker n'a pas répondu à temps.", job_id)


_DFS_REFUSALS = {
    "DFS_ADMIN_REQUIRED": status.HTTP_403_FORBIDDEN,
    "DFS_FOLDER_EXISTS": status.HTTP_409_CONFLICT,
    "DFS_FOLDER_INVALID": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "DFS_TARGET_INVALID": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "DFS_NAMESPACE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
}


class DfsFolderPayload(BaseModel):
    # Under the namespace: Corporate\\Finance
    folder: str = Field(min_length=1, max_length=255)
    # The share it leads to: \\\\FILER01\\Finance
    target: str = Field(min_length=5, max_length=512)


def _save_dfs_links(endpoint: StorageEndpoint, links: list[dict[str, Any]]) -> None:
    from app.services.dfs_links import forget_cache

    capabilities = dict(endpoint.capabilities or {})
    capabilities["dfs_snapshot"] = {**dict(capabilities.get("dfs_snapshot") or {}), "links": links}
    endpoint.capabilities = capabilities
    forget_cache()


def _dfs_operation(db: Session, request: Request, endpoint_id: int, action: str, folder: str, **context: Any):
    from app.services.dfs_links import snapshot

    endpoint = _dfs_endpoint(db, endpoint_id)
    if not (endpoint.bind_dn and endpoint.bind_password_ref):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "ENDPOINT_CREDENTIALS_MISSING", "message": "Le serveur DFS n'a pas de compte."})
    shot = snapshot(endpoint)
    path = str(shot.get("path") or "").strip().rstrip("\\")
    folder = folder.strip().strip("\\")
    operation = _EndpointOperation(db, request, endpoint, action=action, share=folder,
                                   context={"folder": folder, "dfs_path": f"{path}\\{folder}", **context})
    if not path:
        raise operation.refused(status.HTTP_409_CONFLICT, "DFS_NAMESPACE_NOT_READ", "Read the namespace before changing it")
    error = dfs_folder_error(folder)
    if error:
        raise operation.refused(status.HTTP_422_UNPROCESSABLE_ENTITY, "DFS_FOLDER_INVALID", error)
    links = [dict(link) for link in (shot.get("links") or []) if isinstance(link, dict)]
    return endpoint, operation, path, folder, links


def _remember_dfs_delegation(endpoint: StorageEndpoint, denied: bool) -> None:
    """The last answer of the namespace on the right to manage it: shown in « To do » until a change goes through."""
    from datetime import datetime, timezone

    capabilities = dict(endpoint.capabilities or {})
    answer = {"at": datetime.now(timezone.utc).isoformat(), "account": endpoint.bind_dn}
    # The refusal, or the last change that went through (« management delegated, checked on … » in the header)
    if denied:
        capabilities["dfs_manage_denied"] = answer
        capabilities.pop("dfs_manage_ok", None)
    else:
        capabilities.pop("dfs_manage_denied", None)
        capabilities["dfs_manage_ok"] = answer
    endpoint.capabilities = capabilities


async def _run_dfs_job(operation: _EndpointOperation, endpoint: StorageEndpoint, protocol: str, target: dict[str, Any], failure_code: str):
    try:
        await operation.run(protocol, "", failure_code=failure_code, kind="dfs-folder",
                            target={"host": endpoint.host, "port": int(endpoint.port or 445), **target})
        _remember_dfs_delegation(endpoint, denied=False)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = str(detail.get("code") or "")
        if code == "DFS_ADMIN_REQUIRED":
            _remember_dfs_delegation(endpoint, denied=True)
            operation.db.commit()
        if code in _DFS_REFUSALS and exc.status_code != _DFS_REFUSALS[code]:
            raise HTTPException(status_code=_DFS_REFUSALS[code], detail=detail) from exc
        raise


@router.post("/{endpoint_id}/dfs-folders", status_code=status.HTTP_201_CREATED, dependencies=[Depends(admin_only)])
async def create_dfs_folder(endpoint_id: int, payload: DfsFolderPayload, request: Request, db: Session = Depends(get_db)):
    """Create a DFS folder under the namespace, leading to a share. The account of the namespace must be allowed to manage it."""
    target = payload.target.strip().replace("/", "\\").rstrip("\\")
    endpoint, operation, path, folder, links = _dfs_operation(db, request, endpoint_id, "storage_endpoint.dfs_folder_created",
                                                              payload.folder, target=target)
    parts = [part for part in target.split("\\") if part]
    if not target.startswith("\\\\") or len(parts) < 2:
        raise operation.refused(status.HTTP_422_UNPROCESSABLE_ENTITY, "DFS_TARGET_INVALID", "The target is a network path such as \\\\server\\share")
    same = next((link for link in links if str(link.get("path") or "").lower() == folder.lower()), None)
    if same and any(str(t).lower() == target.lower() for t in (same.get("targets") or [])):
        raise operation.refused(status.HTTP_409_CONFLICT, "DFS_FOLDER_EXISTS", "This DFS folder already leads to this target")
    await _run_dfs_job(operation, endpoint, "create", {"path": path, "folder": folder, "target_unc": target}, "DFS_FOLDER_CREATE_FAILED")
    if same:
        same["targets"] = [*(same.get("targets") or []), target]
    else:
        links.append({"path": folder, "targets": [target]})
    _save_dfs_links(endpoint, links)
    operation.log("success")
    db.commit()
    return ui_data({"path": f"{path}\\{folder}", "target": target})


@router.delete("/{endpoint_id}/dfs-folders", dependencies=[Depends(admin_only)])
async def delete_dfs_folder(endpoint_id: int, folder: str, request: Request, db: Session = Depends(get_db)):
    """Remove a DFS folder and all its targets. The shares and their files are not touched; refused while it is managed."""
    from app.services.dfs_links import describe_links

    endpoint, operation, path, folder, links = _dfs_operation(db, request, endpoint_id, "storage_endpoint.dfs_folder_deleted", folder)
    link = next((row for row in describe_links(db, endpoint) if str(row.get("path") or "").lower() == folder.lower()), None)
    if link is None:
        raise operation.refused(status.HTTP_404_NOT_FOUND, "DFS_FOLDER_NOT_FOUND", "This DFS folder is not in the last reading of the namespace")
    if any(target.get("storage_root_id") for target in link.get("targets") or []):
        raise operation.refused(status.HTTP_409_CONFLICT, "DFS_FOLDER_MANAGED",
                                "BornToShare manages the folders behind this DFS folder: its users reach them through it")
    targets = [str(target.get("unc")) for target in link.get("targets") or [] if target.get("unc")]
    await _run_dfs_job(operation, endpoint, "delete", {"path": path, "folder": folder, "targets": targets}, "DFS_FOLDER_DELETE_FAILED")
    _save_dfs_links(endpoint, [row for row in links if str(row.get("path") or "").lower() != folder.lower()])
    operation.log("success", targets=targets)
    db.commit()
    return ui_data({"path": f"{path}\\{folder}", "targets": targets})


@router.post("/{endpoint_id}/shares", status_code=status.HTTP_201_CREATED, dependencies=[Depends(admin_only)])
async def create_endpoint_share(endpoint_id: int, payload: ShareCreatePayload, request: Request, db: Session = Depends(get_db)):
    """Create a share on the file server with its account, which must be a local administrator of the server."""
    endpoint = _share_endpoint(db, endpoint_id)
    name = payload.name.strip()
    local_path = (payload.path or "").strip() or f"C:\\Shares\\{name}"
    operation = _EndpointOperation(db, request, endpoint, action="storage_endpoint.share_created", share=name,
                                context={"share": name, "path": local_path})
    error = share_name_error(name)
    if error:
        # Refused here, before a job: the worker would give the same answer
        raise operation.refused(status.HTTP_422_UNPROCESSABLE_ENTITY, "SHARE_NAME_INVALID", error)
    await operation.run("create", local_path, failure_code="SHARE_CREATE_FAILED")
    unc = f"\\\\{endpoint.host}\\{name}"
    # Listed at once with the shares of the server, without searching it again
    capabilities = endpoint.capabilities if isinstance(endpoint.capabilities, dict) else {}
    snapshot = capabilities.get("discovered_roots_snapshot")
    if isinstance(snapshot, dict) and isinstance(snapshot.get("roots"), list):
        roots = [root for root in snapshot["roots"] if normalize_root_path(str((root or {}).get("root_path") or "")) != normalize_root_path(unc)]
        roots.append({"root_path": unc, "name": name})
        endpoint.capabilities = {**capabilities, "discovered_roots_snapshot": {**snapshot, "roots": roots, "roots_count": len(roots)}}
    operation.log("success")
    db.commit()
    return ui_data({"share": name, "path": local_path, "unc": unc})


@router.delete("/{endpoint_id}/shares/{share}", dependencies=[Depends(admin_only)])
async def delete_endpoint_share(endpoint_id: int, share: str, request: Request, remove_empty_folder: bool = False,
                                db: Session = Depends(get_db)):
    """Remove a share from the file server. Its folder and files stay on the server; refused while BornToShare manages a folder in it."""
    endpoint = _share_endpoint(db, endpoint_id)
    name = share.strip()
    unc = f"\\\\{endpoint.host}\\{name}"
    operation = _EndpointOperation(db, request, endpoint, action="storage_endpoint.share_deleted", share=name,
                                context={"share": name, "unc": unc})
    if share_name_error(name) or name.endswith("$"):
        raise operation.refused(status.HTTP_422_UNPROCESSABLE_ENTITY, "SHARE_NAME_INVALID", "This share cannot be deleted from BornToShare")
    prefix = normalize_root_path(unc)
    managed = [
        str(path) for (path,) in db.execute(
            text("SELECT root_path FROM storage_roots WHERE storage_endpoint_id = :id AND deleted_at IS NULL "
                 "AND (normalized_root_path = :prefix OR normalized_root_path LIKE :below)"),
            {"id": int(endpoint_id), "prefix": prefix, "below": prefix + "/%"},
        ).all()
    ]
    if managed:
        raise operation.refused(status.HTTP_409_CONFLICT, "SHARE_HAS_STORAGE_ROOTS",
                                f"{len(managed)} folder(s) of this share are managed in BornToShare: remove them first",
                                roots=len(managed))
    job = await operation.run("delete", unc, failure_code="SHARE_DELETE_FAILED",
                              target={"host": endpoint.host, "share": name, "path": unc, "remove_empty_folder": bool(remove_empty_folder)})
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    folder_removed = bool((result.get("details") or {}).get("folder_removed"))
    # The last search of the server still lists it: gone from there too
    capabilities = endpoint.capabilities if isinstance(endpoint.capabilities, dict) else {}
    snapshot = capabilities.get("discovered_roots_snapshot")
    if isinstance(snapshot, dict) and isinstance(snapshot.get("roots"), list):
        kept = [root for root in snapshot["roots"] if normalize_root_path(str((root or {}).get("root_path") or "")) != prefix]
        endpoint.capabilities = {**capabilities, "discovered_roots_snapshot": {**snapshot, "roots": kept, "roots_count": len(kept)}}
    operation.log("success", folder_removed=folder_removed)
    db.commit()
    return ui_data({"share": name, "unc": unc, "folder_removed": folder_removed})


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

    secret_ref = endpoint.bind_password_ref
    db.delete(endpoint)
    db.flush()
    forget_unused(db, [secret_ref])
    db.execute(text("DELETE FROM infra_component_status WHERE component = :c"), {"c": f"storage_endpoint:{int(endpoint_id)}"})
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
