from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, load_only

from app.core.db import get_db
from app.core.logging import get_logger, log_event
from app.models.identity_sources import IdentitySource
from app.models.storage_endpoint import StorageEndpoint
from app.repositories.identity_sources_views_repo import IdentitySourcesViewsRepo
from app.routers._helpers import ui_action, ui_data, ui_list
from app.schemas.identity_sources import (
    IdentitySourceCreate,
    IdentitySourceUpdate,
    IdentitySourceTestResult,
    IdentitySourceTestCheck,
)
from app.services.governance_proxy import gov_post
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request

router = APIRouter(prefix="/identity-sources", tags=["identity_sources"])
logger = get_logger("dal.identity_sources")


def _actor_from_headers(request: Request) -> tuple[int | None, str | None]:
    actor = actor_from_request(request)
    return actor.identity_id, actor.display_name
def _status_from_active(is_active: bool | None) -> str:
    return "active" if bool(is_active) else "disabled"


def _identity_source_available_columns(db: Session) -> set[str]:
    try:
        inspector = inspect(db.get_bind())
        return {col["name"] for col in inspector.get_columns(IdentitySource.__tablename__)}
    except Exception:
        return set()


def _source_capabilities(src: IdentitySource) -> dict[str, object]:
    raw = src.__dict__.get("capabilities")
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _source_auth_enabled(src: IdentitySource, caps: dict[str, object] | None = None) -> bool:
    if "auth_enabled" in src.__dict__:
        return bool(src.__dict__.get("auth_enabled"))
    effective_caps = caps if isinstance(caps, dict) else _source_capabilities(src)
    return bool(effective_caps.get("auth", False))


def _source_auth_priority(src: IdentitySource) -> int:
    if "auth_priority" in src.__dict__:
        raw = src.__dict__.get("auth_priority")
        try:
            return int(raw or 100)
        except Exception:
            return 100
    return 100


async def _trigger_initial_snapshot_via_governance(request: Request, source_id: int) -> None:
    """Dispatch initial directory snapshot job through Governance/Capsule path (best effort)."""
    await gov_post(
        request=request,
        path="/identity/snapshots/run",
        payload={
            "identity_source_id": int(source_id),
            "mode": "auto",
            "force_full": True,
        },
    )


def _identity_source_load_only(db: Session):
    try:
        available = _identity_source_available_columns(db)
        if not available:
            return None
        attrs = [
            getattr(IdentitySource, col.name)
            for col in IdentitySource.__table__.columns
            if col.name in available
        ]
        return load_only(*attrs) if attrs else None
    except Exception:
        return None


def _get_identity_source(db: Session, source_id: int) -> IdentitySource | None:
    query = db.query(IdentitySource)
    load_opt = _identity_source_load_only(db)
    if load_opt is not None:
        query = query.options(load_opt)
    return query.filter(IdentitySource.id == source_id).first()


def _public_row(src: IdentitySource) -> dict:
    caps = _source_capabilities(src)
    auth_enabled = _source_auth_enabled(src, caps)
    auth_priority = _source_auth_priority(src)
    return {
        "id": src.id,
        "type": src.type,
        "name": src.name,
        "domain_name": src.domain_name,
        "external_id": src.external_id,
        "status": str(src.status or _status_from_active(getattr(src, "is_active", True))),
        "protocol": src.protocol,
        "host": src.host,
        "port": src.port,
        "base_dn": src.base_dn,
        "bind_dn": src.bind_dn,
        "issuer_url": getattr(src, "issuer_url", None),
        "last_probe_at": src.last_probe_at.isoformat() if src.last_probe_at else None,
        "last_probe_message": src.last_probe_message,
        "last_snapshot_at": None,
        "last_snapshot_status": None,
        "used": False,
        "auth_enabled": auth_enabled,
        "auth_priority": auth_priority,
        "capabilities": {
            "auth": auth_enabled,
            "import_groups": bool(caps.get("import_groups", True)),
            "snapshot_enabled": bool(caps.get("snapshot_enabled", False)),
        },
        "is_active": bool(src.is_active),
    }


def _empty_snapshot_meta() -> dict[str, str | int | None]:
    return IdentitySourcesViewsRepo.empty_latest_snapshot_meta()


def _latest_snapshot_meta(db: Session | None, source_id: int) -> dict[str, str | int | None]:
    if db is None:
        return _empty_snapshot_meta()
    return IdentitySourcesViewsRepo(db).get_latest_snapshot_meta(int(source_id))


def _is_identity_source_used(db: Session, src: IdentitySource) -> bool:
    source_id = int(getattr(src, "id", 0) or 0)
    if source_id <= 0:
        return False
    linked_endpoint = (
        db.query(StorageEndpoint.id)
        .filter(StorageEndpoint.identity_source_id == source_id)
        .limit(1)
        .first()
    )
    return linked_endpoint is not None


def _identity_source_dependency_counts(db: Session, source_id: int) -> dict[str, int]:
    source_key = int(source_id or 0)
    if source_key <= 0:
        return {}

    checks = {
        "storage endpoints": ("storage_endpoints", "identity_source_id"),
        "application identities": ("identities", "source_id"),
        "directory OUs": ("directory_ous", "identity_source_id"),
        "directory users": ("directory_users", "identity_source_id"),
        "directory groups": ("directory_groups", "identity_source_id"),
    }
    counts: dict[str, int] = {}
    for label, (table_name, column_name) in checks.items():
        try:
            count = db.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = :source_id"),
                {"source_id": source_key},
            ).scalar()
        except Exception:
            continue
        numeric = int(count or 0)
        if numeric > 0:
            counts[label] = numeric
    return counts


def _identity_source_dependency_message(counts: dict[str, int]) -> str:
    if not counts:
        return "Identity source is used and cannot be deleted"
    parts = [f"{count} {label}" for label, count in counts.items()]
    return "Identity source cannot be deleted while related records exist: " + ", ".join(parts)


def _purge_identity_source_related_records(db: Session, source_id: int) -> None:
    source_key = int(source_id or 0)
    if source_key <= 0:
        return

    statements = [
        """
        DELETE arie
        FROM access_request_item_executions arie
        JOIN access_requests ar
          ON ar.id = arie.access_request_id
        JOIN identities i
          ON i.id = ar.requester_identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE ari
        FROM access_request_items ari
        JOIN access_requests ar
          ON ar.id = ari.access_request_id
        JOIN identities i
          ON i.id = ar.requester_identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE ar
        FROM access_requests ar
        JOIN identities i
          ON i.id = ar.requester_identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE sr
        FROM storage_root_roles sr
        JOIN identities i
          ON i.id = sr.identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE ir
        FROM identity_roles ir
        LEFT JOIN identities i
          ON i.id = ir.identity_id
        LEFT JOIN directory_groups dg
          ON dg.id = ir.directory_group_id
        WHERE i.source_id = :source_id
           OR dg.identity_source_id = :source_id
        """,
        """
        DELETE lc
        FROM local_credentials lc
        JOIN identities i
          ON i.id = lc.identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE ib
        FROM identity_bindings ib
        LEFT JOIN identities i
          ON i.id = ib.identity_id
        LEFT JOIN directory_users du
          ON du.id = ib.directory_user_id
        WHERE i.source_id = :source_id
           OR du.identity_source_id = :source_id
        """,
        """
        DELETE dem
        FROM directory_effective_memberships dem
        LEFT JOIN directory_users du
          ON du.id = dem.directory_user_id
        LEFT JOIN directory_groups dg
          ON dg.id = dem.directory_group_id
        WHERE dem.identity_source_id = :source_id
           OR du.identity_source_id = :source_id
           OR dg.identity_source_id = :source_id
           OR dem.snapshot_id IN (
             SELECT ds.id
             FROM directory_snapshots ds
             WHERE ds.identity_source_id = :source_id
           )
        """,
        """
        DELETE dsm
        FROM directory_snapshot_memberships dsm
        JOIN directory_snapshots ds
          ON ds.id = dsm.snapshot_id
        WHERE ds.identity_source_id = :source_id
        """,
        """
        DELETE dsg
        FROM directory_snapshot_groups dsg
        JOIN directory_snapshots ds
          ON ds.id = dsg.snapshot_id
        WHERE ds.identity_source_id = :source_id
        """,
        """
        DELETE dsu
        FROM directory_snapshot_users dsu
        JOIN directory_snapshots ds
          ON ds.id = dsu.snapshot_id
        WHERE ds.identity_source_id = :source_id
        """,
        """
        DELETE dgm
        FROM directory_group_members dgm
        LEFT JOIN directory_groups dg
          ON dg.id = dgm.group_id
        LEFT JOIN directory_users du
          ON du.id = dgm.directory_user_id
        WHERE dg.identity_source_id = :source_id
           OR du.identity_source_id = :source_id
        """,
        """
        DELETE FROM directory_snapshots
        WHERE identity_source_id = :source_id
        """,
        """
        DELETE FROM directory_ous
        WHERE identity_source_id = :source_id
        """,
        """
        DELETE FROM directory_groups
        WHERE identity_source_id = :source_id
        """,
        """
        DELETE FROM directory_users
        WHERE identity_source_id = :source_id
        """,
        """
        DELETE FROM identities
        WHERE source_id = :source_id
        """,
    ]
    for statement in statements:
        db.execute(text(statement), {"source_id": source_key})


@router.get("", summary="List identity sources")
def list_identity_sources(db: Session = Depends(get_db)):
    query = db.query(IdentitySource)
    load_opt = _identity_source_load_only(db)
    if load_opt is not None:
        query = query.options(load_opt)
    rows = query.order_by(IdentitySource.id.desc()).all()

    latest_snapshot_map = IdentitySourcesViewsRepo(db).list_latest_snapshot_meta_by_source()

    results = []
    for r in rows:
        payload = _public_row(r)
        payload.update(latest_snapshot_map.get(int(r.id), _empty_snapshot_meta()))
        payload["used"] = _is_identity_source_used(db, r)
        results.append(payload)
    return ui_list(results)


@router.get("/{source_id}/internal", summary="Get identity source (internal, with secrets)")
def get_identity_source_internal(source_id: int, db: Session = Depends(get_db)):
    src = _get_identity_source(db, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="Identity source not found")
    caps = _source_capabilities(src)
    auth_enabled = _source_auth_enabled(src, caps)
    auth_priority = _source_auth_priority(src)
    snapshot_meta = _latest_snapshot_meta(db, int(src.id))
    payload = {
        "id": src.id,
        "type": src.type,
        "name": src.name,
        "domain_name": src.domain_name,
        "external_id": src.external_id,
        "protocol": src.protocol,
        "host": src.host,
        "port": src.port,
        "base_dn": src.base_dn,
        "bind_dn": src.bind_dn,
        "bind_password": None,
        "bind_password_ref": src.bind_password_ref,
        "issuer_url": getattr(src, "issuer_url", None),
        "last_snapshot_at": snapshot_meta.get("last_snapshot_at"),
        "last_snapshot_status": snapshot_meta.get("last_snapshot_status"),
        "last_snapshot_version": snapshot_meta.get("last_snapshot_version") or getattr(src, "last_snapshot_version", None),
        "last_snapshot_users_count": snapshot_meta.get("last_snapshot_users_count"),
        "last_snapshot_groups_count": snapshot_meta.get("last_snapshot_groups_count"),
        "last_snapshot_memberships_count": snapshot_meta.get("last_snapshot_memberships_count"),
        "last_snapshot_objects_count": snapshot_meta.get("last_snapshot_objects_count"),
        "auth_enabled": auth_enabled,
        "auth_priority": auth_priority,
        "capabilities": {
            "auth": auth_enabled,
            "import_groups": bool(caps.get("import_groups", True)),
            "snapshot_enabled": bool(caps.get("snapshot_enabled", False)),
            "auth_mode": caps.get("auth_mode", "ntlm"),
        },
        "is_active": bool(src.is_active),
    }
    return ui_data(payload, meta={"source_id": int(source_id)})


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create identity source")
def create_identity_source(payload: IdentitySourceCreate, request: Request, db: Session = Depends(get_db)):
    available_columns = _identity_source_available_columns(db)
    has_auth_enabled_col = "auth_enabled" in available_columns
    has_auth_priority_col = "auth_priority" in available_columns

    if payload.bind_password:
        raise HTTPException(
            status_code=400,
            detail="Plaintext secrets are not allowed. Use bind_password_ref.",
        )
    if payload.type == "ad" and bool(payload.auth_enabled) and not payload.bind_password_ref:
        raise HTTPException(
            status_code=400,
            detail="bind_password_ref is required when auth_enabled=true for AD identity sources.",
        )
    source_type = str(payload.type or "ad").strip().lower()
    is_active = bool(payload.is_active)
    bind_password_ref = str(payload.bind_password_ref or "").strip() or None
    auth_enabled = bool(payload.auth_enabled)
    auth_priority = int(payload.auth_priority)

    capabilities_payload = payload.capabilities.model_dump()
    capabilities_payload["auth"] = auth_enabled

    create_data: dict[str, object] = {
        "type": source_type,
        "name": payload.name,
        "domain_name": payload.domain_name,
        "external_id": payload.external_id,
        "protocol": payload.protocol,
        "host": payload.host,
        "port": payload.port,
        "base_dn": payload.base_dn,
        "bind_dn": payload.bind_dn,
        "bind_password_ref": bind_password_ref,
        "issuer_url": getattr(payload, "issuer_url", None),
        "capabilities": capabilities_payload,
        "status": _status_from_active(is_active),
        "is_active": is_active,
    }
    if has_auth_enabled_col:
        create_data["auth_enabled"] = auth_enabled
    if has_auth_priority_col:
        create_data["auth_priority"] = auth_priority

    src = IdentitySource(**create_data)
    db.add(src)
    db.commit()
    db.refresh(src)

    # Trigger initial snapshot asynchronously via Governance/Capsule (best effort)
    # only when snapshot capability is explicitly enabled.
    source_caps = src.capabilities if isinstance(src.capabilities, dict) else {}
    if str(src.type or "").lower() == "ad" and bool(source_caps.get("snapshot_enabled", False)):
        try:
            import asyncio

            asyncio.run(_trigger_initial_snapshot_via_governance(request, int(src.id)))
        except Exception as exc:
            log_event(
                logger,
                30,
                "DAL_IDENTITY_SOURCE_SNAPSHOT_TRIGGER_FAILED",
                action="identity_source_create_snapshot_trigger",
                outcome="error",
                identity_source_id=int(src.id),
                message=str(exc),
            )

    actor_id, actor_display = _actor_from_headers(request)
    created_auth_enabled = _source_auth_enabled(src)
    created_auth_priority = _source_auth_priority(src)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="identity_source.created",
        outcome="success",
        target_type="identity_source",
        target_id=int(src.id),
        target_display=str(src.name or src.host or src.id),
        context_json={
            "type": src.type,
            "domain_name": src.domain_name,
            "external_id": src.external_id,
            "protocol": src.protocol,
            "host": src.host,
            "port": src.port,
            "auth_enabled": created_auth_enabled,
            "auth_priority": created_auth_priority,
            "is_active": bool(src.is_active),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(action_id=int(src.id), message="identity_source.created")


@router.delete("/{source_id}", summary="Delete identity source")
def delete_identity_source(source_id: int, request: Request, db: Session = Depends(get_db)):
    src = _get_identity_source(db, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="Identity source not found")
    _purge_identity_source_related_records(db, int(src.id))
    dependency_counts = _identity_source_dependency_counts(db, int(src.id))
    if dependency_counts:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": _identity_source_dependency_message(dependency_counts),
                "dependencies": dependency_counts,
            },
        )
    target_display = str(src.name or src.host or src.id)
    context = {
        "type": src.type,
        "domain_name": src.domain_name,
        "external_id": src.external_id,
        "protocol": src.protocol,
        "host": src.host,
        "port": src.port,
        "is_active": bool(src.is_active),
    }
    db.delete(src)
    db.commit()

    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="identity_source.deleted",
        outcome="success",
        target_type="identity_source",
        target_id=int(source_id),
        target_display=target_display,
        context_json=context,
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(action_id=int(source_id), message="identity_source.deleted")


@router.patch("/{source_id}", summary="Update identity source")
def update_identity_source(
    source_id: int,
    payload: IdentitySourceUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    available_columns = _identity_source_available_columns(db)
    has_auth_enabled_col = "auth_enabled" in available_columns
    has_auth_priority_col = "auth_priority" in available_columns

    src = _get_identity_source(db, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="Identity source not found")

    if payload.bind_password:
        raise HTTPException(
            status_code=400,
            detail="Plaintext secrets are not allowed. Use bind_password_ref.",
        )

    if src.type == "ad" and payload.bind_dn is not None:
        next_ref = payload.bind_password_ref or src.bind_password_ref
        if not next_ref and _source_auth_enabled(src):
            raise HTTPException(
                status_code=400,
                detail="bind_password_ref is required for AD identity sources.",
            )

    if src.type == "ad":
        payload_auth_enabled = payload.auth_enabled
        next_auth_enabled = _source_auth_enabled(src) if payload_auth_enabled is None else bool(payload_auth_enabled)
        next_ref = payload.bind_password_ref if payload.bind_password_ref is not None else src.bind_password_ref
        next_ref = str(next_ref or "").strip() or None
        if next_auth_enabled and not next_ref:
            raise HTTPException(
                status_code=400,
                detail="bind_password_ref is required when auth_enabled=true for AD identity sources.",
            )

    updates_raw = payload.model_dump(exclude_unset=True)
    updates_raw.pop("bind_password", None)

    capabilities = updates_raw.pop("capabilities", None)
    if capabilities is not None:
        if hasattr(capabilities, "model_dump"):
            updates_raw["capabilities"] = capabilities.model_dump()
        else:
            updates_raw["capabilities"] = dict(capabilities)

    allowed_update_fields = {
        "name",
        "domain_name",
        "external_id",
        "protocol",
        "host",
        "port",
        "base_dn",
        "bind_dn",
        "bind_password_ref",
        "issuer_url",
        "capabilities",
        "auth_enabled",
        "auth_priority",
        "is_active",
    }
    disallowed_fields = [k for k in updates_raw.keys() if k not in allowed_update_fields]
    if disallowed_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported update field(s): {', '.join(sorted(disallowed_fields))}",
        )

    updates = {k: v for k, v in updates_raw.items() if k in allowed_update_fields}

    requested_auth_enabled = updates.get("auth_enabled") if "auth_enabled" in updates else None

    if "auth_enabled" in updates:
        updates["auth_enabled"] = bool(updates.get("auth_enabled"))
    if "auth_priority" in updates:
        updates["auth_priority"] = int(updates.get("auth_priority") or 100)

    if "capabilities" in updates or "auth_enabled" in updates:
        next_caps = _source_capabilities(src)
        if "capabilities" in updates and isinstance(updates.get("capabilities"), dict):
            next_caps.update(updates.get("capabilities") or {})
        next_caps["auth"] = bool(requested_auth_enabled) if requested_auth_enabled is not None else _source_auth_enabled(src)
        updates["capabilities"] = next_caps

    if not has_auth_enabled_col:
        updates.pop("auth_enabled", None)
    if not has_auth_priority_col:
        updates.pop("auth_priority", None)

    if "bind_password_ref" in updates:
        updates["bind_password_ref"] = str(updates.get("bind_password_ref") or "").strip() or None
    if "is_active" in updates:
        updates["status"] = _status_from_active(bool(updates.get("is_active")))

    if _is_identity_source_used(db, src):
        critical_fields = {"protocol", "host", "port", "base_dn"}
        changed_critical = sorted([k for k in updates.keys() if k in critical_fields])
        if changed_critical:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Identity source is used by storage endpoints and critical connection fields "
                    f"cannot be changed: {', '.join(changed_critical)}"
                ),
            )

    before = {
        "name": src.name,
        "domain_name": src.domain_name,
        "external_id": src.external_id,
        "host": src.host,
        "protocol": src.protocol,
        "port": src.port,
        "auth_enabled": _source_auth_enabled(src),
        "auth_priority": _source_auth_priority(src),
        "is_active": bool(src.is_active),
        "status": src.status,
    }

    for field, value in updates.items():
        setattr(src, field, value)

    db.commit()

    after = {
        "name": src.name,
        "domain_name": src.domain_name,
        "external_id": src.external_id,
        "host": src.host,
        "protocol": src.protocol,
        "port": src.port,
        "auth_enabled": _source_auth_enabled(src),
        "auth_priority": _source_auth_priority(src),
        "is_active": bool(src.is_active),
        "status": src.status,
    }
    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="identity_source.updated",
        outcome="success",
        target_type="identity_source",
        target_id=int(src.id),
        target_display=str(src.name or src.host or src.id),
        context_json={
            "before": before,
            "after": after,
            "updated_fields": sorted(list(updates.keys())),
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(action_id=int(source_id), message="identity_source.updated")


@router.post("/test", summary="Test identity source configuration (no persistence)")
async def test_identity_source(payload: IdentitySourceCreate, request: Request):
    res = await gov_post(
        request=request,
        path="/identity-sources/test",
        payload=payload.model_dump(exclude={"bind_password"}, exclude_none=True),
    )

    checks = [IdentitySourceTestCheck(**c) for c in (res.get("checks") or [])]
    result = IdentitySourceTestResult(ok=bool(res.get("ok")), checks=checks)
    return ui_data(result.model_dump())


@router.get("/{source_id}/groups", summary="Search AD groups")
async def get_groups(request: Request, source_id: int, q: str = Query(default="", max_length=190), db: Session = Depends(get_db)):
    src = _get_identity_source(db, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="Identity source not found")
    if src.type != "ad":
        raise HTTPException(status_code=400, detail="This identity source is not AD")

    payload = {
        "identity_source_id": int(source_id),
        "query": str(q or "").strip(),
        "limit": 25,
        "principal_type": "group",
        "search_scope": "subtree",
    }
    result = await gov_post(
        request=request,
        path="/identity/search",
        payload=payload,
    )

    groups = []
    for row in (result or {}).get("groups") if isinstance(result, dict) else []:
        if not isinstance(row, dict):
            continue
        dn = str(row.get("dn") or row.get("external_id") or "").strip()
        if not dn:
            continue
        name = str(row.get("display_name") or row.get("username") or dn).strip()
        groups.append(
            {
                "name": name,
                "dn": dn,
                "samaccountname": str(row.get("username") or "").strip() or None,
            }
        )
    return ui_list(groups, meta={"source_id": int(source_id), "query": str(q or "").strip(), "count": int(len(groups))})
