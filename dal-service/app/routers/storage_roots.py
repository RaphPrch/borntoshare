from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.db import get_db
from app.core.internal_auth import require_internal_token
from app.models.identity import Identity
from app.models.storage_endpoint import StorageEndpoint
from app.models.storage_root import StorageRoot
from app.models.storage_root_access_profile import StorageRootAccessProfile
from app.models.storage_root_role import StorageRootRole
from app.schemas.storage_root import (
    StorageRootCreate,
    StorageRootUpdate,
)
from app.repositories.storage_roots_views_repo import StorageRootsViewsRepo
from app.repositories.storage_root_owners_repo import StorageRootOwnersRepo
from app.repositories.governance_alerts_repo import GovernanceAlertsRepo
from app.routers._helpers import ui_action, ui_data, ui_list
from app.services.activity_log import log_activity
from app.services.authorization import (
    actor_from_request,
    filter_storage_root_rows,
    require_admin,
    require_storage_root_access,
    require_storage_roots_index,
)
from app.services.access_profiles_v1 import SYSTEM_MANAGED_ERROR
from app.services.naming_policy import resolve_effective_policy
from app.services.probe_results import ProbeResultService, normalize_probe_status_value
from app.services.storage_root_binding_materialization_service import (
    materialize_root_bindings,
)

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


class StorageRootOwnersUpdatePayload(BaseModel):
    guardian_ids: list[int] = Field(default_factory=list)


class StorageRootRoleAssignPayload(BaseModel):
    identity_id: int = Field(..., ge=1)
    role: Literal["guardian"]


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


def _serialize_root_access_profiles(
    *,
    db: Session,
    storage_root_id: int,
) -> dict:
    return StorageRootsViewsRepo(db).serialize_access_profiles(storage_root_id=int(storage_root_id))


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


def _list_ad_group_members_for_storage_root(
    db: Session,
    *,
    storage_root_id: int,
    group_ref: str,
) -> tuple[list[dict[str, Any]], int | None, str]:
    return StorageRootsViewsRepo(db).list_ad_group_members(
        storage_root_id=int(storage_root_id),
        group_ref=group_ref,
    )


def _project_storage_root_ad_groups(
    *,
    db: Session,
    storage_root_id: int,
    access_profiles_state: dict[str, Any],
    include_members: bool = False,
    include_expected: bool = False,
) -> list[dict[str, Any]]:
    return StorageRootsViewsRepo(db).project_ad_groups(
        storage_root_id=int(storage_root_id),
        access_profiles_state=access_profiles_state,
        include_members=bool(include_members),
        include_expected=bool(include_expected),
    )


def _normalize_root_path(value: str | None) -> str:
    raw = str(value or "").strip().replace("/", "\\")
    while "\\\\" in raw:
        raw = raw.replace("\\\\", "\\")
    return raw.rstrip("\\").lower()


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

    Legacy note:
    - access_profiles are no longer part of the active public UI contract
    - governed groups remain exposed through projected_ad_groups
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
    access_profiles_state = _serialize_root_access_profiles(db=db, storage_root_id=int(storage_root_id))
    provisioning_policy = _get_effective_provisioning_policy(db=db, storage_root_id=int(storage_root_id))
    projected_groups = _project_storage_root_ad_groups(
        db=db,
        storage_root_id=int(storage_root_id),
        access_profiles_state=access_profiles_state,
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

    access_profiles_state = _serialize_root_access_profiles(db=db, storage_root_id=int(storage_root_id))
    groups = _project_storage_root_ad_groups(
        db=db,
        storage_root_id=int(storage_root_id),
        access_profiles_state=access_profiles_state,
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


@router.get("/{storage_root_id}/ad-groups/members")
def get_storage_root_ad_group_members(
    storage_root_id: int,
    request: Request,
    group_name: str = Query(..., min_length=1, max_length=256),
    db: Session = Depends(get_db),
):
    require_storage_root_access(db, actor_from_request(request), int(storage_root_id))
    root = db.get(StorageRoot, int(storage_root_id))
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage root not found",
        )

    normalized_group = str(group_name or "").strip()
    if not normalized_group:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="group_name is required",
        )

    members, active_snapshot_id, members_source = _list_ad_group_members_for_storage_root(
        db,
        storage_root_id=int(storage_root_id),
        group_ref=normalized_group,
    )

    return ui_data(
        {
            "storage_root_id": int(storage_root_id),
            "group_name": normalized_group,
            "active_snapshot_id": active_snapshot_id,
            "members_source": members_source,
            "members_count": len(members),
            "members": members,
        },
        meta={"storage_root_id": int(storage_root_id), "count": int(len(members))},
    )

@router.get("/{storage_root_id}/effective-access")
def get_storage_root_effective_access(
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
    payload = {
        "storage_root_id": storage_root_id,
        **repo.get_effective_access_details(storage_root_id),
    }
    return ui_data(payload, meta={"storage_root_id": int(storage_root_id)})


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


@router.get("/{storage_root_id}/access-profiles")
def list_storage_root_access_profiles(
    storage_root_id: int,
    db: Session = Depends(get_db),
):
    """Legacy compatibility endpoint for storage-root access-profile bindings."""
    root = db.get(StorageRoot, int(storage_root_id))
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    payload = _serialize_root_access_profiles(db=db, storage_root_id=int(storage_root_id))
    count = int(len(payload.get("items") or []))
    return ui_data(
        payload,
        meta={
            "storage_root_id": int(storage_root_id),
            "count": count,
            "deprecated": True,
        },
    )


@router.post("/{storage_root_id}/access-profiles/{access_profile_id:int}")
async def attach_storage_root_access_profile(
    storage_root_id: int,
    access_profile_id: int,
):
    """Legacy system-managed endpoint kept temporarily for compatibility."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error_code": "SYSTEM_MANAGED_ROUTE",
            "message": SYSTEM_MANAGED_ERROR,
            "details": {
                "storage_root_id": int(storage_root_id),
                "access_profile_id": int(access_profile_id),
            },
        },
    )


@router.delete("/{storage_root_id}/access-profiles/{access_profile_id:int}")
def detach_storage_root_access_profile(
    storage_root_id: int,
    access_profile_id: int,
    db: Session = Depends(get_db),
):
    """Legacy compatibility endpoint for detaching a local access-profile binding."""
    root = db.get(StorageRoot, int(storage_root_id))
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")

    link = (
        db.query(StorageRootAccessProfile)
        .filter(
            StorageRootAccessProfile.storage_root_id == int(storage_root_id),
            StorageRootAccessProfile.access_profile_id == int(access_profile_id),
            StorageRootAccessProfile.deleted_at.is_(None),
        )
        .first()
    )
    if link:
        if str(getattr(link, "source", "LOCAL") or "LOCAL").upper() in {"ZONE", "INHERITED"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Inherited zone profile is read-only on storage root",
            )
        link.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        link.active = False
        db.add(link)

    db.commit()
    _reconcile_storage_root_alerts(db, int(storage_root_id))
    payload = _serialize_root_access_profiles(db=db, storage_root_id=int(storage_root_id))
    count = int(len(payload.get("items") or []))
    return ui_data(
        payload,
        meta={
            "storage_root_id": int(storage_root_id),
            "count": count,
            "deprecated": True,
        },
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


@router.post("/{storage_root_id}/roles")
def assign_storage_root_role(
    storage_root_id: int,
    payload: StorageRootRoleAssignPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_platform_admin(request)

    root = db.get(StorageRoot, int(storage_root_id))
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")

    identity = db.get(Identity, int(payload.identity_id))
    if identity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")

    _guardians_in_active_snapshot_enabled(
        db,
        storage_root_id=int(storage_root_id),
        guardian_ids=[int(payload.identity_id)],
    )

    actor = actor_from_request(request)
    actor_id, actor_display = actor.identity_id, actor.display_name

    row = StorageRootRole(
        root_id=int(storage_root_id),
        identity_id=int(payload.identity_id),
        role=str(payload.role).lower(),
        assigned_by=actor_id,
    )
    db.add(row)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

    repo = StorageRootsViewsRepo(db)
    owners = repo.list_owners(int(storage_root_id))

    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_root.role.assigned",
        outcome="success",
        target_type="storage_root",
        target_id=int(storage_root_id),
        target_display=str(root.name or root.root_path or root.id),
        context_json={
            "identity_id": int(payload.identity_id),
            "role": str(payload.role).lower(),
            "owners_count": len(owners),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )

    _reconcile_storage_root_alerts(db, int(storage_root_id))

    return ui_data(
        {
            "storage_root_id": int(storage_root_id),
            "owners": owners,
        },
        meta={"storage_root_id": int(storage_root_id), "count": int(len(owners))},
    )


@router.delete("/{storage_root_id}/roles/{role}/{identity_id}")
def remove_storage_root_role(
    storage_root_id: int,
    role: str,
    identity_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_platform_admin(request)

    normalized_role = str(role or "").strip().lower()
    if normalized_role != "guardian":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="role must be guardian")

    root = db.get(StorageRoot, int(storage_root_id))
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")

    actor = actor_from_request(request)
    actor_id, actor_display = actor.identity_id, actor.display_name

    db.execute(
        text(
            """
            DELETE FROM storage_root_roles
            WHERE root_id = :root_id
              AND identity_id = :identity_id
              AND LOWER(role) = :role
            """
        ),
        {
            "root_id": int(storage_root_id),
            "identity_id": int(identity_id),
            "role": normalized_role,
        },
    )
    db.commit()

    repo = StorageRootsViewsRepo(db)
    owners = repo.list_owners(int(storage_root_id))

    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="storage_root.role.removed",
        outcome="success",
        target_type="storage_root",
        target_id=int(storage_root_id),
        target_display=str(root.name or root.root_path or root.id),
        context_json={
            "identity_id": int(identity_id),
            "role": normalized_role,
            "owners_count": len(owners),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )

    _reconcile_storage_root_alerts(db, int(storage_root_id))

    return ui_data(
        {
            "storage_root_id": int(storage_root_id),
            "owners": owners,
        },
        meta={"storage_root_id": int(storage_root_id), "count": int(len(owners))},
    )


@router.get("/applied-access")
def list_storage_roots_applied_access(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    READ MODEL — Applied access (GLOBAL).
    Backed by table: storage_root_roles
    """
    actor = actor_from_request(request)
    require_storage_roots_index(db, actor)
    repo = StorageRootsViewsRepo(db)
    rows = repo.list_applied_access()
    rows = filter_storage_root_rows(db, actor, rows)
    return ui_list(rows, meta={"count": int(len(rows))})


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

    Legacy note:
    - access_profiles are no longer part of the active public UI contract
    - governed groups remain exposed through projected_ad_groups
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
    access_profiles_state = _serialize_root_access_profiles(db=db, storage_root_id=int(storage_root_id))
    row["owners"] = repo.list_owners(storage_root_id)
    row["projected_ad_groups"] = _project_storage_root_ad_groups(
        db=db,
        storage_root_id=int(storage_root_id),
        access_profiles_state=access_profiles_state,
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
            "inherit_access_profiles": bool(root.inherit_access_profiles),
            "is_active": _root_is_active(root),
            "zone_id": _root_zone_id(root),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
        background=False,
    )

    zone_id = int(endpoint.zone_id) if endpoint and endpoint.zone_id is not None else None
    if zone_id:
        materialize_root_bindings(
            db,
            storage_root_id=int(root.id),
            replace_stale=True,
            commit=True,
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
        "inherit_access_profiles": bool(root.inherit_access_profiles),
        "is_active": _root_is_active(root),
        "zone_id": _root_zone_id(root),
    }
    updates = payload.model_dump(exclude_unset=True)
    if "last_probe_status" in updates:
        updates["last_probe_status"] = _normalize_probe_status_value(updates.get("last_probe_status"))

    target_storage_endpoint_id = int(updates.get("storage_endpoint_id") or root.storage_endpoint_id)
    target_root_path = str(updates.get("root_path") or root.root_path or "")
    if "root_path" in updates or "storage_endpoint_id" in updates:
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

    if any(k in updates for k in {"storage_endpoint_id", "root_path", "name"}):
        materialize_root_bindings(
            db,
            storage_root_id=int(root.id),
            replace_stale=True,
            commit=True,
        )

    after = {
        "name": root.name,
        "root_path": root.root_path,
        "normalized_root_path": root.normalized_root_path,
        "storage_endpoint_id": root.storage_endpoint_id,
        "parent_storage_root_id": root.parent_storage_root_id,
        "inherit_owners": bool(root.inherit_owners),
        "inherit_tags": bool(root.inherit_tags),
        "inherit_access_profiles": bool(root.inherit_access_profiles),
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

    children = _child_storage_roots(db, parent_storage_root_id=int(root.id))
    if children:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storage root has child storage roots attached and cannot be deleted",
        )

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
