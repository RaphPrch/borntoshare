from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.db import get_db
from app.core.internal_auth import require_internal_token
from app.data.models.identity import Identity
from app.data.models.storage_endpoint import StorageEndpoint
from app.data.models.storage_root import StorageRoot
from app.schemas.storage_root import (
    StorageRootCreate,
    StorageRootUpdate,
)
from app.data.repositories.storage_roots_views_repo import StorageRootsViewsRepo
from app.data.repositories.storage_root_owners_repo import StorageRootOwnersRepo
from app.data.repositories.governance_alerts_repo import GovernanceAlertsRepo
from app.api._helpers import ui_action, ui_data, ui_list
from app.services.activity_log import log_activity
from app.services.authorization import (
    actor_from_request,
    filter_storage_root_rows,
    require_admin,
    require_storage_root_access,
    require_storage_roots_index,
)
from app.services.naming_policy import resolve_effective_policy
from app.services.probe_results import ProbeResultService, normalize_probe_status_value
from app.services.storage_root_permissions import StorageRootPermissions
from app.services.storage_guards import root_access_counts, root_access_group_count, same_host, unc_host

router = APIRouter(
    prefix="/storage-roots",
    tags=["storage_roots"],
)


def _reconcile_storage_root_alerts(db: Session, storage_root_id: int) -> None:
    GovernanceAlertsRepo(db).reconcile_storage_root(int(storage_root_id), commit=True)


def _normalize_probe_status_value(value: object) -> str | None:
    return normalize_probe_status_value(value)


def _require_platform_admin(request: Request) -> None:
    require_admin(actor_from_request(request))


def _load_active_enabled_snapshot_users(
    db: Session,
    *,
    identity_source_id: int,
) -> set[int]:
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ib.identity_id
            FROM directory_snapshots ds
            JOIN directory_snapshot_users dsu
              ON dsu.snapshot_id = ds.id
            JOIN directory_users du
              ON du.identity_source_id = dsu.identity_source_id
             AND (
                  LOWER(TRIM(COALESCE(du.external_id, ''))) = LOWER(TRIM(COALESCE(dsu.external_id, '')))
               OR LOWER(TRIM(COALESCE(du.dn, ''))) = LOWER(TRIM(COALESCE(dsu.dn, '')))
             )
            JOIN identity_bindings ib
              ON ib.directory_user_id = du.id
            WHERE ds.identity_source_id = :identity_source_id
              AND UPPER(COALESCE(ds.status, '')) IN ('ACTIVE', 'SUCCEEDED')
              AND COALESCE(dsu.is_active, 0) = 1
              AND COALESCE(ib.identity_id, 0) > 0
            """
        ),
        {"identity_source_id": int(identity_source_id)},
    ).mappings().all()
    out: set[int] = set()
    for row in rows:
        try:
            identity_id = int(row.get("identity_id") or 0)
        except Exception:
            identity_id = 0
        if identity_id > 0:
            out.add(identity_id)
    return out


def _guardians_in_active_snapshot_enabled(
    db: Session,
    *,
    storage_root_id: int,
    guardian_ids: list[int],
) -> None:
    requested = sorted({int(v) for v in (guardian_ids or []) if int(v) > 0})
    if not requested:
        return

    row = db.execute(
        text(
            """
            SELECT se.identity_source_id
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            WHERE sr.id = :storage_root_id
            LIMIT 1
            """
        ),
        {"storage_root_id": int(storage_root_id)},
    ).mappings().first()
    identity_source_id = int((row or {}).get("identity_source_id") or 0)
    if identity_source_id <= 0:
        # Identity source is optional on storage roots in V1.
        # If absent, skip snapshot-based guardian validation.
        return

    eligible = _load_active_enabled_snapshot_users(db, identity_source_id=identity_source_id)
    invalid = [identity_id for identity_id in requested if identity_id not in eligible]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Guardians must belong to active snapshot and be enabled users. "
                f"Invalid identity ids: {','.join(str(v) for v in invalid)}"
            ),
        )


def _load_existing_guardian_ids(
    db: Session,
    *,
    storage_root_id: int,
) -> set[int]:
    rows = db.execute(
        text(
            """
            SELECT DISTINCT srr.identity_id
            FROM storage_root_roles srr
            WHERE srr.root_id = :storage_root_id
              AND LOWER(srr.role) = 'guardian'
            """
        ),
        {"storage_root_id": int(storage_root_id)},
    ).mappings().all()

    out: set[int] = set()
    for row in rows:
        try:
            identity_id = int(row.get("identity_id") or 0)
        except Exception:
            identity_id = 0
        if identity_id > 0:
            out.add(identity_id)
    return out


def _guardian_ids_requiring_snapshot_validation(
    db: Session,
    *,
    storage_root_id: int,
    guardian_ids: list[int],
) -> list[int]:
    requested = sorted({int(v) for v in (guardian_ids or []) if int(v) > 0})
    if not requested:
        return []

    existing_guardians = _load_existing_guardian_ids(
        db,
        storage_root_id=int(storage_root_id),
    )
    return [identity_id for identity_id in requested if identity_id not in existing_guardians]


def _root_is_active(root: StorageRoot) -> bool:
    """Lifecycle flag derived from `status` only (V1 simplified model)."""
    status_value = str(getattr(root, "status", "active") or "").strip().lower()
    return status_value not in {"inactive", "disabled", "error"}


def _root_zone_id(root: StorageRoot) -> int | None:
    """Resolve zone_id from relationship when StorageRoot has no direct zone_id column."""
    if hasattr(root, "zone_id"):
        value = getattr(root, "zone_id")
        return int(value) if value is not None else None
    endpoint = getattr(root, "storage_endpoint", None)
    if endpoint is None:
        return None
    value = getattr(endpoint, "zone_id", None)
    return int(value) if value is not None else None


def _root_zone_name(db: Session, zone_id: int | None) -> str | None:
    if not zone_id:
        return None
    return db.execute(text("SELECT name FROM zones WHERE id = :id"), {"id": int(zone_id)}).scalar()


class StorageRootOwnersUpdatePayload(BaseModel):
    guardian_ids: list[int] = Field(default_factory=list)


class StorageRootDiscoveryItem(BaseModel):
    root_path: str
    permissions: list[dict] = Field(default_factory=list)


class StorageRootDiscoverySyncPayload(BaseModel):
    storage_endpoint_id: int
    discovered_at: str | None = None
    discovery_complete: bool = True
    roots: list[StorageRootDiscoveryItem] = Field(default_factory=list)


class StorageRootProbeResultPayload(BaseModel):
    last_probe_status: str = Field(..., max_length=32)
    last_probe_at: str | None = None
    last_probe_message: str | None = Field(default=None, max_length=512)
    last_probe_job_id: int | None = None
    source_type: str | None = Field(default=None, max_length=80)


def _derive_root_name_from_path(value: str) -> str:
    normalized = str(value or "").strip().rstrip("\\/")
    if not normalized:
        return ""
    parts = [chunk for chunk in normalized.replace("\\", "/").split("/") if chunk]
    return parts[-1] if parts else normalized


def _extract_discovered_roots_snapshot(items: list[StorageRootDiscoveryItem]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in items:
        root_path = str(getattr(item, "root_path", "") or "").strip()
        if not root_path:
            continue
        key = _normalize_root_path(root_path)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "root_path": root_path,
                "name": _derive_root_name_from_path(root_path),
            }
        )

    return out


def _persist_endpoint_discovery_snapshot(
    db: Session,
    *,
    storage_endpoint_id: int,
    discovered_at: datetime,
    payload: StorageRootDiscoverySyncPayload,
) -> dict[str, Any] | None:
    endpoint = db.get(StorageEndpoint, int(storage_endpoint_id))
    if endpoint is None:
        return None

    raw_caps = getattr(endpoint, "capabilities", None)
    capabilities = dict(raw_caps) if isinstance(raw_caps, dict) else {}

    roots_snapshot = _extract_discovered_roots_snapshot(payload.roots)
    snapshot = {
        "version": 2,
        "status": "success",
        "discovered_at": discovered_at.isoformat(),
        "discovery_complete": bool(payload.discovery_complete),
        "roots_count": len(roots_snapshot),
        "roots": roots_snapshot,
        "last_error": None,
        "updated_by": "storage_roots.discovery_sync",
    }
    capabilities["discovered_roots_snapshot"] = snapshot
    endpoint.capabilities = capabilities
    return snapshot


def _get_effective_provisioning_policy(
    *,
    db: Session,
    storage_root_id: int,
) -> dict | None:
    row = StorageRootsViewsRepo(db).get_effective_provisioning_policy(int(storage_root_id))
    if row is None:
        return None

    zone_id = int(row.get("zone_id") or 0) or None
    storage_endpoint_id = int(row.get("storage_endpoint_id") or 0) or None

    endpoint_identity_source_id = int(row.get("effective_identity_source_id") or 0) or None
    resolved_identity_source_id = endpoint_identity_source_id

    resolved_group_ou = str(row.get("effective_ou_dn") or "").strip() or None
    endpoint_group_ou = None

    effective_naming_policy = resolve_effective_policy(
        db,
        zone_id,
        storage_endpoint_id=storage_endpoint_id,
        storage_root_id=int(storage_root_id),
    )
    resolved_naming_policy = str((effective_naming_policy or {}).get("template") or "").strip() or None

    identity_source_resolution = "endpoint_override" if endpoint_identity_source_id else "zone_default"
    group_ou_resolution = "zone_default"
    naming_policy_resolution = "effective_override_chain"

    effective = {
        "identity_source_id": resolved_identity_source_id,
        "effective_ou_dn": resolved_group_ou,
        "base_parent_ou_dn": resolved_group_ou,
        "endpoint_sub_ou_dn": endpoint_group_ou,
        "naming_template": resolved_naming_policy,
    }
    return {
        "storage_root_id": int(row.get("storage_root_id") or storage_root_id),
        "storage_endpoint_id": int(row.get("storage_endpoint_id") or 0) or None,
        "zone_id": zone_id,
        "resolved_identity_source_id": resolved_identity_source_id,
        "resolved_group_ou": resolved_group_ou,
        "resolved_naming_policy": resolved_naming_policy,
        "resolution_source": {
            "identity_source": identity_source_resolution,
            "group_ou": group_ou_resolution,
            "naming_policy": naming_policy_resolution,
        },
        "effective": effective,
        "effective_preview": {
            "effective_identity_source_id": resolved_identity_source_id,
            "effective_identity_source_name": None,
            "effective_ou_dn": resolved_group_ou,
            "warnings": [] if resolved_group_ou else ["No effective OU configured for this storage root."],
        },
    }


def _active_snapshot_id_for_source(
    db: Session,
    *,
    identity_source_id: int | None,
) -> int | None:
    return StorageRootsViewsRepo(db)._active_snapshot_id_for_source(identity_source_id=identity_source_id)


def _dedupe_group_member_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return StorageRootsViewsRepo._dedupe_group_member_rows(rows)


def _ad_group_exists_for_identity_source(
    db: Session,
    *,
    group_ref: str,
    identity_source_id: int | None,
) -> bool:
    return StorageRootsViewsRepo(db)._ad_group_exists_for_identity_source(
        group_ref=group_ref,
        identity_source_id=identity_source_id,
    )


def _list_group_members_from_effective_memberships(
    db: Session,
    *,
    group_ref: str,
    identity_source_id: int | None,
) -> list[dict[str, Any]]:
    return StorageRootsViewsRepo(db)._list_group_members_from_effective_memberships(
        group_ref=group_ref,
        identity_source_id=identity_source_id,
    )


def _list_group_members_from_directory_group_members(
    db: Session,
    *,
    group_ref: str,
    identity_source_id: int | None,
) -> list[dict[str, Any]]:
    return StorageRootsViewsRepo(db)._list_group_members_from_directory_group_members(
        group_ref=group_ref,
        identity_source_id=identity_source_id,
    )


def _list_group_members_from_active_snapshot_payload(
    db: Session,
    *,
    group_ref: str,
    identity_source_id: int | None,
) -> list[dict[str, Any]]:
    return StorageRootsViewsRepo(db)._list_group_members_from_active_snapshot_payload(
        group_ref=group_ref,
        identity_source_id=identity_source_id,
    )


def _project_storage_root_ad_groups(
    *,
    db: Session,
    storage_root_id: int,
    include_members: bool = False,
    include_expected: bool = False,
) -> list[dict[str, Any]]:
    return StorageRootsViewsRepo(db).project_ad_groups(
        storage_root_id=int(storage_root_id),
        include_members=bool(include_members),
        include_expected=bool(include_expected),
    )


def _normalize_root_path(value: str | None) -> str:
    raw = str(value or "").strip().replace("/", "\\")
    while "\\\\" in raw:
        raw = raw.replace("\\\\", "\\")
    return raw.rstrip("\\").lower()


def _assert_root_on_endpoint_host(db: Session, *, storage_endpoint_id: int, root_path: str) -> None:
    """The UNC host of a storage root is the host of its file server (fs12 and fs12.example.org match)."""
    host = unc_host(root_path)
    if not host:
        return
    endpoint_host = db.execute(
        text("SELECT host FROM storage_endpoints WHERE id = :id"), {"id": int(storage_endpoint_id)}
    ).scalar()
    if endpoint_host and not same_host(host, endpoint_host):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STORAGE_ROOT_HOST_MISMATCH",
                "message": f"The path points at {host}, but the file server is {endpoint_host}",
                "root_host": host,
                "endpoint_host": endpoint_host,
            },
        )


def _normalize_storage_root_path(value: str | None) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    while "//" in raw:
        raw = raw.replace("//", "/")
    return raw.rstrip("/").lower()


def _is_child_root_path(*, child: str, parent: str) -> bool:
    child_path = _normalize_storage_root_path(child)
    parent_path = _normalize_storage_root_path(parent)
    return bool(child_path and parent_path and child_path != parent_path and child_path.startswith(parent_path + "/"))


def _resolve_parent_storage_root_id(
    db: Session,
    *,
    storage_endpoint_id: int,
    normalized_root_path: str,
    exclude_root_id: int | None = None,
) -> int | None:
    normalized = _normalize_storage_root_path(normalized_root_path)
    if not normalized:
        return None

    rows = db.execute(
        text(
            """
            SELECT id, normalized_root_path, root_path
            FROM storage_roots
            WHERE storage_endpoint_id = :storage_endpoint_id
              AND (:exclude_root_id IS NULL OR id <> :exclude_root_id)
              AND deleted_at IS NULL
            """
        ),
        {
            "storage_endpoint_id": int(storage_endpoint_id),
            "exclude_root_id": int(exclude_root_id) if exclude_root_id else None,
        },
    ).mappings().all()

    candidates: list[tuple[int, str]] = []
    for row in rows:
        parent_norm = _normalize_storage_root_path(row.get("normalized_root_path") or row.get("root_path"))
        if not parent_norm or parent_norm == normalized:
            continue
        if normalized.startswith(parent_norm + "/"):
            candidates.append((int(row.get("id") or 0), parent_norm))

    if not candidates:
        return None

    candidates.sort(key=lambda item: len(item[1]), reverse=True)
    return candidates[0][0] or None


def _assert_unique_storage_root_path(
    db: Session,
    *,
    storage_endpoint_id: int,
    normalized_root_path: str,
    exclude_root_id: int | None = None,
) -> None:
    normalized = _normalize_storage_root_path(normalized_root_path)
    if not normalized:
        return
    row = db.execute(
        text(
            """
            SELECT id
            FROM storage_roots
            WHERE storage_endpoint_id = :storage_endpoint_id
              AND COALESCE(NULLIF(normalized_root_path, ''), LOWER(TRIM(TRAILING '/' FROM REPLACE(root_path, '\\\\', '/')))) = :normalized_root_path
              AND (:exclude_root_id IS NULL OR id <> :exclude_root_id)
              AND deleted_at IS NULL
            LIMIT 1
            """
        ),
        {
            "storage_endpoint_id": int(storage_endpoint_id),
            "normalized_root_path": normalized,
            "exclude_root_id": int(exclude_root_id) if exclude_root_id else None,
        },
    ).mappings().first()
    if row:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "STORAGE_ROOT_PATH_CONFLICT",
                "message": "Storage root already exists for this endpoint/path",
                "storage_endpoint_id": int(storage_endpoint_id),
                "normalized_root_path": normalized,
                "existing_storage_root_id": int(row.get("id") or 0) or None,
            },
        )


def _validate_parent_storage_root(
    db: Session,
    *,
    parent_storage_root_id: int | None,
    storage_endpoint_id: int,
    root_path: str,
    exclude_root_id: int | None = None,
) -> int | None:
    if parent_storage_root_id is None:
        return None

    parent_id = int(parent_storage_root_id)
    if exclude_root_id is not None and int(exclude_root_id) == parent_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="parent_storage_root_id cannot reference the storage root itself",
        )

    parent = db.get(StorageRoot, parent_id)
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="parent_storage_root_id does not reference an existing storage root",
        )

    if int(parent.storage_endpoint_id) != int(storage_endpoint_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="parent storage root must belong to the same storage endpoint",
        )

    if not _is_child_root_path(child=root_path, parent=str(parent.root_path or "")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="storage root path must be nested under its parent storage root path",
        )

    ancestor_id = int(parent.parent_storage_root_id or 0)
    seen: set[int] = {parent_id}
    while ancestor_id > 0:
        if exclude_root_id is not None and ancestor_id == int(exclude_root_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="parent_storage_root_id would create a storage root cycle",
            )
        if ancestor_id in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="storage root hierarchy contains a cycle",
            )
        seen.add(ancestor_id)
        ancestor = db.get(StorageRoot, ancestor_id)
        ancestor_id = int(getattr(ancestor, "parent_storage_root_id", 0) or 0) if ancestor else 0

    return parent_id


def _child_storage_roots(db: Session, *, parent_storage_root_id: int) -> list[dict[str, Any]]:
    return list(
        db.execute(
            text(
                """
                SELECT id, name, root_path, storage_endpoint_id
                FROM storage_roots
                WHERE parent_storage_root_id = :parent_storage_root_id
                  AND deleted_at IS NULL
                ORDER BY name, id
                """
            ),
            {"parent_storage_root_id": int(parent_storage_root_id)},
        ).mappings().all()
    )


def _validate_child_storage_roots_remain_nested(
    db: Session,
    *,
    parent_storage_root_id: int,
    storage_endpoint_id: int,
    root_path: str,
) -> None:
    children = _child_storage_roots(db, parent_storage_root_id=int(parent_storage_root_id))
    for child in children:
        if int(child.get("storage_endpoint_id") or 0) != int(storage_endpoint_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot move a storage root to another endpoint while child storage roots are attached",
            )
        if not _is_child_root_path(child=str(child.get("root_path") or ""), parent=root_path):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot update storage root path because child storage roots would no longer be nested",
            )


def _parse_discovered_at(value: str | None) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except Exception:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ============================================================
# READ MODELS (V2.1+ — VIEWS ONLY)
# ============================================================

@router.get("/context")
def list_storage_roots_context(
    request: Request,
    zone_id: int | None = None,
    db: Session = Depends(get_db),
):
    """
    Context list for Storage Roots UI.

    Backed by base tables.

    IMPORTANT:
    - One row per storage_root
    - No ORM joins
    - No aggregation here
    """
    actor = actor_from_request(request)
    require_storage_roots_index(db, actor)
    repo = StorageRootsViewsRepo(db)
    rows = repo.list_context(zone_id=zone_id)
    rows = filter_storage_root_rows(db, actor, rows)
    return ui_list(
        rows,
        meta={
            "zone_id": int(zone_id) if zone_id is not None else None,
            "count": int(len(rows)),
        },
    )


@router.get("/{storage_root_id}/overview")
def get_storage_root_overview(
    storage_root_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Full overview for a single storage root.

    Backed by base tables.

    AD groups (created ones, plus the names levels will get on first request)
    are exposed through projected_ad_groups.
    """
    require_storage_root_access(db, actor_from_request(request), int(storage_root_id))
    repo = StorageRootsViewsRepo(db)
    row = repo.get_overview(storage_root_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage root not found",
        )

    effective_access = repo.get_effective_access_details(storage_root_id)
    provisioning_policy = _get_effective_provisioning_policy(db=db, storage_root_id=int(storage_root_id))
    projected_groups = _project_storage_root_ad_groups(
        db=db,
        storage_root_id=int(storage_root_id),
    )
    row["owners"] = repo.list_owners(storage_root_id)
    row["projected_ad_groups"] = projected_groups
    row["acl_freshness"] = repo.get_acl_freshness(storage_root_id)
    row["provisioning_policy"] = provisioning_policy
    row["effective_provisioning"] = {
        "identity_source_id": (provisioning_policy or {}).get("resolved_identity_source_id"),
        "group_ou": (provisioning_policy or {}).get("resolved_group_ou"),
        "naming_policy": (provisioning_policy or {}).get("resolved_naming_policy"),
    }
    row["effective_access"] = effective_access.get("users", [])
    row["effective_access_counts"] = {
        "read_users": int(effective_access.get("read_users") or 0),
        "write_users": int(effective_access.get("write_users") or 0),
        "total_users": int(effective_access.get("total_users") or 0),
    }

    return ui_data(row, meta={"storage_root_id": int(storage_root_id)})


@router.get("/{storage_root_id}/ad-groups")
def get_storage_root_ad_groups(
    storage_root_id: int,
    request: Request,
    include_members: bool = Query(True),
    include_expected: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_storage_root_access(db, actor_from_request(request), int(storage_root_id))
    root = db.get(StorageRoot, int(storage_root_id))
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage root not found",
        )

    groups = _project_storage_root_ad_groups(
        db=db,
        storage_root_id=int(storage_root_id),
        include_members=bool(include_members),
        include_expected=bool(include_expected),
    )

    return ui_data(
        {
            "storage_root_id": int(storage_root_id),
            "groups_count": len(groups),
            "groups": groups,
        },
        meta={"storage_root_id": int(storage_root_id), "count": int(len(groups))},
    )


@router.get("/{storage_root_id}/owners")
def get_storage_root_owners(
    storage_root_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    require_storage_root_access(db, actor_from_request(request), int(storage_root_id))
    root = db.get(StorageRoot, storage_root_id)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage root not found",
        )

    repo = StorageRootsViewsRepo(db)
    owners = repo.list_owners(storage_root_id)
    return ui_data(
        {
            "storage_root_id": storage_root_id,
            "owners": owners,
        },
        meta={"storage_root_id": int(storage_root_id), "count": int(len(owners))},
    )


@router.put("/{storage_root_id}/owners")
def replace_storage_root_owners(
    storage_root_id: int,
    payload: StorageRootOwnersUpdatePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    root = db.get(StorageRoot, storage_root_id)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage root not found",
        )

    all_ids = {
        int(v)
        for v in (payload.guardian_ids or [])
        if int(v) > 0
    }

    if all_ids:
        existing = {
            identity_id
            for identity_id in all_ids
            if db.get(Identity, identity_id) is not None
        }
        missing = sorted(v for v in all_ids if v not in existing)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown identity ids: {','.join(str(v) for v in missing)}",
            )

    _guardians_in_active_snapshot_enabled(
        db,
        storage_root_id=int(storage_root_id),
        guardian_ids=_guardian_ids_requiring_snapshot_validation(
            db,
            storage_root_id=int(storage_root_id),
            guardian_ids=[int(v) for v in (payload.guardian_ids or []) if int(v) > 0],
        ),
    )

    actor = actor_from_request(request)
    actor_id, actor_display = actor.identity_id, actor.display_name

    write_repo = StorageRootOwnersRepo(db)
    write_repo.replace_owners(
        storage_root_id=storage_root_id,
        guardian_ids=payload.guardian_ids or [],
        assigned_by=actor_id,
    )
    db.commit()

    read_repo = StorageRootsViewsRepo(db)
    owners = read_repo.list_owners(storage_root_id)

    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_root.owners.replaced",
        outcome="success",
        target_type="storage_root",
        target_id=int(storage_root_id),
        target_display=str(root.name or root.root_path or root.id),
        context_json={
            "guardian_ids": sorted({int(v) for v in (payload.guardian_ids or []) if int(v) > 0}),
            "owners_count": len(owners),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )

    _reconcile_storage_root_alerts(db, int(storage_root_id))

    return ui_data(
        {
            "storage_root_id": storage_root_id,
            "owners": owners,
        },
        meta={"storage_root_id": int(storage_root_id), "count": int(len(owners))},
    )


@router.get("/effective-access")
def list_storage_roots_effective_access(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Compatibility alias for the Storage Roots page.

    The page needs a global guardian access list for non-admin
    visibility filtering. Keep the response contract aligned with
    /storage-roots/applied-access.
    """
    actor = actor_from_request(request)
    require_storage_roots_index(db, actor)
    repo = StorageRootsViewsRepo(db)
    rows = repo.list_applied_access()
    rows = filter_storage_root_rows(db, actor, rows)
    return ui_list(rows, meta={"count": int(len(rows))})


@router.post("/discovery-sync", dependencies=[Depends(require_internal_token)])
def sync_storage_root_discovery(
    payload: StorageRootDiscoverySyncPayload,
    db: Session = Depends(get_db),
):
    discovered_at = _parse_discovered_at(payload.discovered_at)

    roots = (
        db.query(StorageRoot)
        .filter(StorageRoot.storage_endpoint_id == int(payload.storage_endpoint_id))
        .all()
    )
    by_path = {_normalize_root_path(r.root_path): r for r in roots}
    discovered_keys: set[str] = set()

    updated = 0
    marked_unreachable = 0
    unmatched: list[str] = []
    probe_results = ProbeResultService(db)

    for item in payload.roots:
        key = _normalize_root_path(item.root_path)
        discovered_keys.add(key)
        root = by_path.get(key)
        if root is None:
            unmatched.append(item.root_path)
            continue
        root.last_probe_status = "success"
        root.last_probe_at = discovered_at
        root.last_probe_message = "discovery_ok"
        root.last_discovery_at = discovered_at
        root.needs_revalidation = False
        root.revalidation_reason = None
        previous_payload = dict(root.discovered_permissions_json or {}) if isinstance(root.discovered_permissions_json, dict) else {}
        root.discovered_permissions_json = {
            "discovered_at": discovered_at.isoformat(),
            "permissions": item.permissions or [],
            "content_size_bytes": previous_payload.get("content_size_bytes"),
            "content_updated_at": previous_payload.get("content_updated_at"),
        }
        probe_results.record_storage_root_probe(
            root,
            status_value="success",
            checked_at=discovered_at,
            message="discovery_ok",
            source_type="storage_root_discovery_sync",
            source_id=str(int(payload.storage_endpoint_id)),
            metadata_json={
                "permissions_count": len(item.permissions or []),
            },
            reconcile_alerts=False,
        )
        updated += 1

    if payload.discovery_complete:
        # Any root attached to the endpoint but not returned by a complete
        # discovery is considered unreachable for this probe cycle.
        for key, root in by_path.items():
            if key in discovered_keys:
                continue
            root.last_probe_status = "failed"
            root.last_probe_at = discovered_at
            root.last_probe_message = "root_not_discovered_or_unreachable"
            root.last_discovery_at = discovered_at
            root.discovered_permissions_json = {
                "discovered_at": discovered_at.isoformat(),
                "permissions": [],
                "probe_error": "root_not_discovered_or_unreachable",
            }
            probe_results.record_storage_root_probe(
                root,
                status_value="failed",
                checked_at=discovered_at,
                message="root_not_discovered_or_unreachable",
                source_type="storage_root_discovery_sync",
                source_id=str(int(payload.storage_endpoint_id)),
                reconcile_alerts=False,
            )
            marked_unreachable += 1

    snapshot = _persist_endpoint_discovery_snapshot(
        db,
        storage_endpoint_id=int(payload.storage_endpoint_id),
        discovered_at=discovered_at,
        payload=payload,
    )

    db.commit()
    for root in roots:
        _reconcile_storage_root_alerts(db, int(root.id))
    return {
        "ok": True,
        "storage_endpoint_id": int(payload.storage_endpoint_id),
        "updated": updated,
        "marked_unreachable": marked_unreachable,
        "unmatched_roots": unmatched,
        "endpoint_snapshot": snapshot,
    }


@router.get("/{storage_root_id}")
def get_storage_root(
    storage_root_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Canonical storage root detail for UI.

    Includes current effective access so the UI can display permissions
    immediately after creation.

    AD groups (created ones, plus the names levels will get on first request)
    are exposed through projected_ad_groups.
    """
    require_storage_root_access(db, actor_from_request(request), int(storage_root_id))
    repo = StorageRootsViewsRepo(db)
    row = repo.get_overview(storage_root_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage root not found",
        )

    effective_access = repo.get_effective_access_details(storage_root_id)
    row["owners"] = repo.list_owners(storage_root_id)
    row["projected_ad_groups"] = _project_storage_root_ad_groups(
        db=db,
        storage_root_id=int(storage_root_id),
    )
    row["acl_freshness"] = repo.get_acl_freshness(storage_root_id)
    row["effective_access"] = effective_access.get("users", [])
    row["effective_access_counts"] = {
        "read_users": int(effective_access.get("read_users") or 0),
        "write_users": int(effective_access.get("write_users") or 0),
        "total_users": int(effective_access.get("total_users") or 0),
    }

    return ui_data(row, meta={"storage_root_id": int(storage_root_id)})

# ============================================================
# WRITE MODEL — CREATE
# ============================================================

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_root(
    payload: StorageRootCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Create a storage root.

    WRITE MODEL ONLY.
    UI must refresh via:
      - GET /storage-roots/context
      - GET /storage-roots/{id}/overview
    """
    data = payload.model_dump()
    if "last_probe_status" in data:
        data["last_probe_status"] = _normalize_probe_status_value(data.get("last_probe_status"))

    normalized_root_path = _normalize_storage_root_path(data.get("root_path"))
    data["normalized_root_path"] = normalized_root_path
    _assert_root_on_endpoint_host(db, storage_endpoint_id=int(data["storage_endpoint_id"]), root_path=str(data.get("root_path") or ""))
    _assert_unique_storage_root_path(
        db,
        storage_endpoint_id=int(data["storage_endpoint_id"]),
        normalized_root_path=normalized_root_path,
    )
    if data.get("parent_storage_root_id") is not None:
        data["parent_storage_root_id"] = _validate_parent_storage_root(
            db,
            parent_storage_root_id=int(data["parent_storage_root_id"]),
            storage_endpoint_id=int(data["storage_endpoint_id"]),
            root_path=str(data["root_path"]),
        )
    else:
        data["parent_storage_root_id"] = _resolve_parent_storage_root_id(
            db,
            storage_endpoint_id=int(data["storage_endpoint_id"]),
            normalized_root_path=normalized_root_path,
        )

    endpoint = db.get(StorageEndpoint, int(data["storage_endpoint_id"]))
    data = ProbeResultService(db).initialize_storage_root_from_endpoint_probe(data, endpoint=endpoint)

    root = StorageRoot(**data)
    db.add(root)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storage root already exists",
        )

    db.refresh(root)
    if root.last_probe_status:
        ProbeResultService(db).record_storage_root_probe(
            root,
            status_value=str(root.last_probe_status),
            checked_at=root.last_probe_at or datetime.now(timezone.utc).replace(tzinfo=None),
            message=root.last_probe_message,
            source_type="storage_root_create",
            source_id=str(root.id),
            reconcile_alerts=False,
        )
        db.commit()

    actor = actor_from_request(request)
    actor_id, actor_display = actor.identity_id, actor.display_name
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_root.created",
        outcome="success",
        target_type="storage_root",
        target_id=int(root.id),
        target_display=str(root.name or root.root_path or root.id),
        context_json={
            "name": root.name,
            "root_path": root.root_path,
            "normalized_root_path": root.normalized_root_path,
            "storage_endpoint_id": root.storage_endpoint_id,
            "parent_storage_root_id": root.parent_storage_root_id,
            "inherit_owners": bool(root.inherit_owners),
            "inherit_tags": bool(root.inherit_tags),
            "is_active": _root_is_active(root),
            "zone_id": _root_zone_id(root),
            # Read by the activity texts (« governed in zone Bordeaux »), not only the id
            "zone_name": _root_zone_name(db, _root_zone_id(root)),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
        background=False,
    )

    _reconcile_storage_root_alerts(db, int(root.id))

    return ui_action(action_id=int(root.id), message="storage_root.created")

# ============================================================
# WRITE MODEL — UPDATE
# ============================================================

@router.patch("/{root_id}")
def update_root(
    root_id: int,
    payload: StorageRootUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Partial update of a storage root.
    """
    root = db.get(StorageRoot, root_id)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage root not found",
        )

    before = {
        "name": root.name,
        "root_path": root.root_path,
        "normalized_root_path": root.normalized_root_path,
        "storage_endpoint_id": root.storage_endpoint_id,
        "parent_storage_root_id": root.parent_storage_root_id,
        "inherit_owners": bool(root.inherit_owners),
        "inherit_tags": bool(root.inherit_tags),
        "is_active": _root_is_active(root),
        "zone_id": _root_zone_id(root),
    }
    updates = payload.model_dump(exclude_unset=True)
    if "last_probe_status" in updates:
        updates["last_probe_status"] = _normalize_probe_status_value(updates.get("last_probe_status"))

    target_storage_endpoint_id = int(updates.get("storage_endpoint_id") or root.storage_endpoint_id)
    target_root_path = str(updates.get("root_path") or root.root_path or "")
    if "root_path" in updates or "storage_endpoint_id" in updates:
        moved = _normalize_storage_root_path(target_root_path) != str(root.normalized_root_path or "") or (
            target_storage_endpoint_id != int(root.storage_endpoint_id)
        )
        if moved:
            groups = root_access_group_count(db, int(root.id))
            if groups:
                # The NTFS ACL and the AD groups stay on the current folder: a new path would not have them
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "STORAGE_ROOT_PATH_LOCKED",
                        "message": f"{groups} AD access group(s) are set on this folder: its path cannot change",
                        "access_groups": groups,
                    },
                )
            _assert_root_on_endpoint_host(db, storage_endpoint_id=target_storage_endpoint_id, root_path=target_root_path)
        updates["normalized_root_path"] = _normalize_storage_root_path(target_root_path)
        _assert_unique_storage_root_path(
            db,
            storage_endpoint_id=target_storage_endpoint_id,
            normalized_root_path=str(updates.get("normalized_root_path") or ""),
            exclude_root_id=int(root.id),
        )
        _validate_child_storage_roots_remain_nested(
            db,
            parent_storage_root_id=int(root.id),
            storage_endpoint_id=target_storage_endpoint_id,
            root_path=target_root_path,
        )

    if "parent_storage_root_id" in updates:
        updates["parent_storage_root_id"] = _validate_parent_storage_root(
            db,
            parent_storage_root_id=(
                int(updates["parent_storage_root_id"])
                if updates.get("parent_storage_root_id") is not None
                else None
            ),
            storage_endpoint_id=target_storage_endpoint_id,
            root_path=target_root_path,
            exclude_root_id=int(root.id),
        )
    elif "root_path" in updates or "storage_endpoint_id" in updates:
        updates["parent_storage_root_id"] = _resolve_parent_storage_root_id(
            db,
            storage_endpoint_id=target_storage_endpoint_id,
            normalized_root_path=str(updates.get("normalized_root_path") or ""),
            exclude_root_id=int(root.id),
        )

    if "last_probe_status" in updates and updates.get("last_probe_status"):
        if str(updates.get("last_probe_status") or "").strip().lower() == "success":
            updates["needs_revalidation"] = False
            updates["revalidation_reason"] = None

    for field, value in updates.items():
        setattr(root, field, value)

    if "last_probe_status" in updates and updates.get("last_probe_status"):
        ProbeResultService(db).record_storage_root_probe(
            root,
            status_value=str(updates.get("last_probe_status") or ""),
            checked_at=updates.get("last_probe_at") or root.last_probe_at or datetime.now(timezone.utc).replace(tzinfo=None),
            message=str(updates.get("last_probe_message") or root.last_probe_message or "").strip() or None,
            source_type="storage_root_update",
            source_id=str(root.id),
            correlation_id=(request.headers.get("x-request-id") or None),
            metadata_json={
                "updated_fields": sorted(list(updates.keys())),
            },
            reconcile_alerts=False,
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storage root already exists for this endpoint/path",
        )

    after = {
        "name": root.name,
        "root_path": root.root_path,
        "normalized_root_path": root.normalized_root_path,
        "storage_endpoint_id": root.storage_endpoint_id,
        "parent_storage_root_id": root.parent_storage_root_id,
        "inherit_owners": bool(root.inherit_owners),
        "inherit_tags": bool(root.inherit_tags),
        "is_active": _root_is_active(root),
        "zone_id": _root_zone_id(root),
    }
    actor = actor_from_request(request)
    actor_id, actor_display = actor.identity_id, actor.display_name
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_root.updated",
        outcome="success",
        target_type="storage_root",
        target_id=int(root.id),
        target_display=str(root.name or root.root_path or root.id),
        context_json={
            "before": before,
            "after": after,
            "updated_fields": sorted(list(updates.keys())),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )

    _reconcile_storage_root_alerts(db, int(root.id))

    return ui_action(action_id=int(root_id), message="storage_root.updated")


@router.post("/{root_id}/probe-result", dependencies=[Depends(require_internal_token)])
def record_storage_root_probe_result(
    root_id: int,
    payload: StorageRootProbeResultPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    root = db.get(StorageRoot, int(root_id))
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage root not found",
        )

    normalized_status = _normalize_probe_status_value(payload.last_probe_status)
    if not normalized_status:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="last_probe_status is required",
        )

    checked_at = _parse_discovered_at(payload.last_probe_at)
    message = str(payload.last_probe_message or "").strip() or None
    root.last_probe_status = normalized_status
    root.last_probe_at = checked_at
    root.last_probe_message = message
    if normalized_status == "success":
        root.last_discovery_at = root.last_discovery_at or checked_at

    ProbeResultService(db).record_storage_root_probe(
        root,
        status_value=normalized_status,
        checked_at=checked_at,
        message=message,
        source_type=str(payload.source_type or "storage_root_probe_result"),
        source_id=str(int(root.id)),
        job_id=int(payload.last_probe_job_id or 0) or None,
        correlation_id=(request.headers.get("x-request-id") or None),
        metadata_json={
            "storage_endpoint_id": int(getattr(root, "storage_endpoint_id", 0) or 0),
            "root_path": getattr(root, "root_path", None),
        },
        reconcile_alerts=False,
    )

    actor = actor_from_request(request)
    actor_id, actor_display = actor.identity_id, actor.display_name
    event_action = "storage_root.probe_completed" if normalized_status == "success" else "storage_root.probe_failed"
    event_target_display = (
        str(root.name or root.root_path or root.id)
        if normalized_status == "success"
        else str(message or root.name or root.root_path or root.id)
    )
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action=event_action,
        outcome="success" if normalized_status == "success" else "failure",
        target_type="storage_root",
        target_id=int(root.id),
        target_display=event_target_display,
        context_json={
            "probe_status": normalized_status,
            "probe_message": message,
            "root_path": root.root_path,
            "storage_endpoint_id": root.storage_endpoint_id,
            "zone_id": _root_zone_id(root),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    db.commit()
    _reconcile_storage_root_alerts(db, int(root.id))

    return ui_data(
        {
            "storage_root_id": int(root.id),
            "last_probe_status": normalized_status,
            "last_probe_at": checked_at.isoformat(),
            "last_probe_message": message,
        },
        meta={"storage_root_id": int(root.id)},
    )

# ============================================================
# WRITE MODEL — DELETE
# ============================================================

# ============================================================
# Permissions (Storage roots › Permissions)
# ============================================================


class AclExceptionPayload(BaseModel):
    principal: str = Field(..., min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=500)


@router.get("/people/search")
def search_people(request: Request, q: str = Query(min_length=2, max_length=100), db: Session = Depends(get_db)):
    """People of the directory and the folders they reach (⌘K); a guardian only sees the folders he guards."""
    actor = actor_from_request(request)
    require_storage_roots_index(db, actor)
    people = StorageRootPermissions(db).search_people(q)
    for person in people:
        person["roots"] = filter_storage_root_rows(db, actor, person["roots"])
    return ui_data(people)


@router.get("/{root_id}/permissions")
def get_root_permissions(root_id: int, request: Request, db: Session = Depends(get_db)):
    """Who reaches the folder and why: people, BornToShare groups and their ACE, system accounts, gaps."""
    require_storage_root_access(db, actor_from_request(request), int(root_id))
    result = StorageRootPermissions(db).build(int(root_id))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    return ui_data(result)


@router.get("/{root_id}/permissions/explain")
def explain_root_access(root_id: int, username: str, request: Request, db: Session = Depends(get_db)):
    """Why a person reaches (or not) the folder: request -> AD group -> ACE -> effective level, step by step."""
    from app.services.activity_bridge import list_activity_by_target

    require_storage_root_access(db, actor_from_request(request), int(root_id))
    service = StorageRootPermissions(db)
    result = service.build(int(root_id))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    wanted = str(username or "").strip().lower()
    person = next(
        (p for p in result["people"] if wanted in {str(p.get("username") or "").lower(), str(p.get("name") or "").lower()}),
        None,
    )
    known = db.execute(
        text("SELECT display_name FROM directory_users WHERE LOWER(username) = :u LIMIT 1"), {"u": wanted}
    ).scalar()
    if person is None:
        return ui_data({"found": False, "username": username, "known_in_directory": bool(known), "display_name": known,
                        "acl_scanned_at": result["acl_scanned_at"], "snapshot_at": result["snapshot_at"]})

    steps: list[dict[str, Any]] = []
    for via in person["via"]:
        if via["kind"] == "request":
            approver = None
            try:
                events = list_activity_by_target(target_type="access_request", target_id=int(via["request_id"]), limit=50)
                approver = next(
                    (e.get("actor_display") for e in events if str(e.get("action")) in {"access_request.approve", "access_request.approved"}),
                    None,
                )
            except Exception:
                approver = None
            steps.append({"kind": "request", **via, "approver": approver})
        elif via["kind"] in {"group", "ad_only", "outside"}:
            group = next((g for g in result["groups"] if g["name"] == via["group"]), None)
            gap = next((g for g in result["gaps"] if g["name"] == via["group"]), None)
            dn = (group or {}).get("dn")
            steps.append({
                "kind": "membership",
                "group": via["group"],
                "managed": via["kind"] != "outside",
                "outside_request": via["kind"] == "ad_only",
                "nested": via.get("nested", False),
                "ou": dn.split(",", 1)[1] if dn and "," in dn else None,
            })
            ace = group or gap
            if ace:
                steps.append({
                    "kind": "ace",
                    "group": via["group"],
                    "state": (group or {}).get("ace", "ok"),
                    "rights_label": ace.get("rights_label"),
                    "inherited_scope": ace.get("inherited_scope", False),
                    "level": via["level"],
                })
    # One step per group / ACE even when several ways lead to it
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for step in steps:
        key = json.dumps(step, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            unique.append(step)
    return ui_data({
        "found": True,
        "person": person,
        "steps": unique,
        "other_roots": service.other_roots(person["username"], int(root_id)) if person.get("username") else [],
        "acl_scanned_at": result["acl_scanned_at"],
        "snapshot_at": result["snapshot_at"],
    })


@router.post("/{root_id}/permissions/exceptions", status_code=status.HTTP_201_CREATED)
def accept_acl_gap(root_id: int, payload: AclExceptionPayload, request: Request, db: Session = Depends(get_db)):
    """« Accept the gap »: an ACL entry added outside BornToShare stops being reported for this folder."""
    actor = actor_from_request(request)
    require_admin(actor)
    root = db.get(StorageRoot, root_id)
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    principal = payload.principal.strip().lower()
    db.execute(
        text(
            """
            INSERT INTO storage_root_acl_exceptions (storage_root_id, principal, note, accepted_by)
            VALUES (:root, :principal, :note, :by)
            ON DUPLICATE KEY UPDATE note = VALUES(note), accepted_by = VALUES(accepted_by), accepted_at = CURRENT_TIMESTAMP
            """
        ),
        {"root": int(root_id), "principal": principal, "note": payload.note, "by": actor.display_name},
    )
    db.commit()
    log_activity(
        db, actor_type="user", actor_id=actor.identity_id, actor_display=actor.display_name,
        action="storage_root.acl_gap_accepted", outcome="success", target_type="storage_root", target_id=int(root_id),
        target_display=str(root.name or root.root_path or root.id),
        context_json={"group_name": payload.principal, "note": payload.note},
    )
    return ui_action(action_id=int(root_id), message="storage_root.acl_gap_accepted")


@router.delete("/{root_id}/permissions/exceptions")
def reopen_acl_gap(root_id: int, principal: str, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    root = db.get(StorageRoot, root_id)
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    db.execute(
        text("DELETE FROM storage_root_acl_exceptions WHERE storage_root_id = :root AND principal = :principal"),
        {"root": int(root_id), "principal": principal.strip().lower()},
    )
    db.commit()
    log_activity(
        db, actor_type="user", actor_id=actor.identity_id, actor_display=actor.display_name,
        action="storage_root.acl_gap_reopened", outcome="success", target_type="storage_root", target_id=int(root_id),
        target_display=str(root.name or root.root_path or root.id), context_json={"group_name": principal},
    )
    return ui_action(action_id=int(root_id), message="storage_root.acl_gap_reopened")


def _ensure_root_deletable(db: Session, root: StorageRoot) -> None:
    accesses = root_access_counts(db, int(root.id))
    if accesses["active"] or accesses["pending"]:
        # Deleting would leave the AD members and the NTFS ACL in place, without any request to revoke them
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STORAGE_ROOT_HAS_ACCESSES",
                "message": f"{accesses['active']} active access(es) and {accesses['pending']} pending request(s) "
                           "on this storage root: revoke or decide them first",
                **accesses,
            },
        )

    children = _child_storage_roots(db, parent_storage_root_id=int(root.id))
    if children:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "STORAGE_ROOT_HAS_CHILDREN", "message": "Storage root has child storage roots attached and cannot be deleted"},
        )


async def _run_folder_job(
    root_id: int, protocol: str, *, inheritance: str | None = None, folder_name: str | None = None, timeout_sec: int = 90
) -> dict[str, Any]:
    """Folder operation of the worker on the file server, waited for; raises a 502 with the worker's message on failure."""
    import asyncio

    from app.services.probe_service import fetch_probe_job, submit_probe_run

    queued = await submit_probe_run({
        "kind": "folder", "protocol": protocol, "scope": "write",
        "target": {"storage_root_id": int(root_id), **({"inheritance": inheritance} if inheritance else {}),
                   **({"folder_name": folder_name} if folder_name else {})},
        "options": {"timeout_sec": timeout_sec}, "context": {"storage_root_id": int(root_id), "ui_origin": "admin"},
    })
    job_id = int((queued or {}).get("job_id") or 0)
    job: dict[str, Any] = {}
    for _ in range(max(1, timeout_sec)):
        job = dict(await fetch_probe_job(job_id) or {})
        state = str(job.get("status") or "").lower()
        if state == "succeeded":
            return job
        if state in {"failed", "timed_out", "cancelled"}:
            break
        await asyncio.sleep(1)
    error = job.get("error") if isinstance(job.get("error"), dict) else {}
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"code": "FOLDER_OPERATION_FAILED", "message": str(error.get("message") or job.get("status") or "the worker did not answer"),
                "job_id": job_id or None},
    )


class InheritancePayload(BaseModel):
    mode: str = Field(pattern="^(break|restore)$")


@router.post("/{root_id}/inheritance")
async def set_root_inheritance(root_id: int, payload: InheritancePayload, request: Request, db: Session = Depends(get_db)):
    """Break (the inherited entries become explicit ones) or restore the NTFS inheritance of the folder, through the worker."""
    actor = actor_from_request(request)
    require_admin(actor)
    root = db.get(StorageRoot, root_id)
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    job = await _run_folder_job(int(root_id), "inheritance", inheritance=payload.mode)
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    details = result.get("details") if isinstance(result.get("details"), dict) else result
    db.refresh(root)
    acl = dict(root.discovered_permissions_json or {}) if isinstance(root.discovered_permissions_json, dict) else {}
    # The state shows at once; the ACL read that follows refreshes the entries
    acl["control"] = str(details.get("control") or ("SR|PD|DP" if payload.mode == "break" else "SR|DP"))
    root.discovered_permissions_json = acl
    db.commit()
    log_activity(
        db, actor_type="user", actor_id=actor.identity_id, actor_display=actor.display_name,
        action=f"storage_root.inheritance_{'broken' if payload.mode == 'break' else 'restored'}", outcome="success",
        target_type="storage_root", target_id=int(root_id), target_display=str(root.name or root.root_path or root.id),
        context_json={"root_path": root.root_path, "job_id": job.get("id")},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_data({"storage_root_id": int(root_id), "inheritance_broken": payload.mode == "break"})


class SubfolderPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # Govern the new folder in BornToShare (a storage root under this one)
    register: bool = True


@router.post("/{root_id}/subfolders", status_code=status.HTTP_201_CREATED)
async def create_root_subfolder(root_id: int, payload: SubfolderPayload, request: Request, db: Session = Depends(get_db)):
    """Create a sub-folder in the folder of the storage root (worker), then, if asked, its storage root."""
    actor = actor_from_request(request)
    require_admin(actor)
    root = db.get(StorageRoot, root_id)
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    name = payload.name
    if name != name.strip() or name in {".", ".."} or name.endswith(".") or any(c in '\\/:*?"<>|' or ord(c) < 32 for c in name):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "FOLDER_NAME_INVALID", "message": 'The folder name contains a character refused by Windows (\\ / : * ? " < > |)'})
    job = await _run_folder_job(int(root_id), "create", folder_name=name)
    path = f"{str(root.root_path or '').rstrip(chr(92))}\\{name}"
    log_activity(
        db, actor_type="user", actor_id=actor.identity_id, actor_display=actor.display_name,
        action="storage_root.subfolder_created", outcome="success", target_type="storage_root", target_id=int(root_id),
        target_display=str(root.name or root.root_path or root.id), context_json={"folder": path, "job_id": job.get("id")},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    created_root_id = None
    if payload.register:
        created = await create_root(
            StorageRootCreate(storage_endpoint_id=int(root.storage_endpoint_id), parent_storage_root_id=int(root.id), name=name, root_path=path),
            request, db,
        )
        created_root_id = int((created or {}).get("data", {}).get("id") or (created or {}).get("id") or 0) or None
    return ui_data({"path": path, "storage_root_id": created_root_id})


class DeleteFolderPayload(BaseModel):
    confirm_name: str = Field(min_length=1, max_length=255)


@router.post("/{root_id}/delete-folder")
async def delete_root_folder(root_id: int, payload: DeleteFolderPayload, request: Request, db: Session = Depends(get_db)):
    """Delete the folder and its content on the file server (worker), then the storage root in BornToShare."""
    actor = actor_from_request(request)
    require_admin(actor)
    root = db.get(StorageRoot, root_id)
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    if payload.confirm_name.strip() != str(root.name or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "CONFIRM_NAME_MISMATCH", "message": "Type the exact name of the storage root to confirm"})
    _ensure_root_deletable(db, root)
    target_display = str(root.name or root.root_path or root.id)
    context = {"name": root.name, "root_path": root.root_path, "storage_endpoint_id": root.storage_endpoint_id,
               "zone_id": _root_zone_id(root), "folder_deleted": True}

    job = await _run_folder_job(int(root_id), "delete", timeout_sec=240)
    db.refresh(root)
    db.delete(root)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"code": "STORAGE_ROOT_REFERENCED", "message": "The folder is deleted but the storage root is still referenced"})
    context["job_id"] = job.get("id")
    log_activity(
        db, actor_type="user", actor_id=actor.identity_id, actor_display=actor.display_name,
        action="storage_root.folder_deleted", outcome="success", target_type="storage_root", target_id=int(root_id),
        target_display=target_display, context_json=context, correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(action_id=int(root_id), message="storage_root.folder_deleted")


@router.delete("/{root_id}")
def delete_root(
    root_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Delete a storage root.
    """
    root = db.get(StorageRoot, root_id)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage root not found",
        )

    target_display = str(root.name or root.root_path or root.id)
    context = {
        "name": root.name,
        "root_path": root.root_path,
        "normalized_root_path": root.normalized_root_path,
        "storage_endpoint_id": root.storage_endpoint_id,
        "parent_storage_root_id": root.parent_storage_root_id,
        "zone_id": _root_zone_id(root),
    }

    _ensure_root_deletable(db, root)

    db.delete(root)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storage root is still referenced by dependent records and cannot be deleted",
        )

    actor = actor_from_request(request)
    actor_id, actor_display = actor.identity_id, actor.display_name
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_root.deleted",
        outcome="success",
        target_type="storage_root",
        target_id=int(root_id),
        target_display=target_display,
        context_json=context,
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(action_id=int(root_id), message="storage_root.deleted")
