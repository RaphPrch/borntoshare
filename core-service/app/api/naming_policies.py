from __future__ import annotations

from typing import Any

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api._helpers import ui_data
from app.services.naming_policy import (
    load_global_policy,
    load_zone_policy,
    resolve_effective_policy,
    resolve_group_name_from_effective_policy,
    resolve_storage_root_naming,
    resolve_zone_context,
    serialize_rootcode_strategy_for_storage,
    validate_template_tokens,
)
from app.services.authorization import admin_or_internal

router = APIRouter(prefix="/naming-policies", tags=["naming_policies"])


def _require_admin(request: Request | None):
    """Only platform administrators change a naming policy (internal calls carry no request)."""
    from app.services.authorization import actor_from_request, require_admin

    if request is None:
        return None
    actor = actor_from_request(request)
    require_admin(actor)
    return actor


def _audit(actor, action: str, *, target_id: Any = None, target_display: str | None = None, context: dict | None = None) -> None:
    from app.services.activity_log import log_activity

    log_activity(
        None,
        actor_type="user" if actor is not None and actor.identity_id is not None else "system",
        actor_id=getattr(actor, "identity_id", None),
        actor_display=getattr(actor, "display_name", None),
        action=action,
        outcome="success",
        target_type="naming_policy",
        target_id=target_id,
        target_display=target_display,
        context_json=context or {},
    )


def _zone_exists(db: Session, zone_id: int) -> bool:
    row = db.execute(
        text(
            """
            SELECT id
            FROM zones
            WHERE id = :zone_id
            LIMIT 1
            """
        ),
        {"zone_id": int(zone_id)},
    ).mappings().first()
    return row is not None


class GlobalNamingPolicyPayload(BaseModel):
    group_prefix: str = Field(default="B2S", min_length=1, max_length=32)
    template: str = Field(default="{PREFIX}_{ROOTCODE}_{PERM}", min_length=1, max_length=128)
    normalize_uppercase: bool = True
    max_sam_length: int = Field(default=64, ge=8, le=255)
    replace_map_json: dict[str, str] | str = Field(default_factory=dict)
    rootcode_strategy: str = Field(default="BASENAME", pattern="^(BASENAME|PATH_ALL)$")


class ZoneNamingPolicyPayload(BaseModel):
    override_enabled: bool = False
    group_prefix: str | None = Field(default=None, max_length=32)
    template: str | None = Field(default=None, max_length=128)
    normalize_uppercase: bool | None = None
    max_sam_length: int | None = Field(default=None, ge=8, le=255)
    replace_map_json: dict[str, str] | str | None = None
    rootcode_strategy: str | None = Field(default=None, pattern="^(BASENAME|PATH_ALL)$")


class NamingPreviewPayload(BaseModel):
    zone_id: str | int
    storage_root_path: str = Field(..., min_length=1, max_length=1024)
    perm: str = Field(..., min_length=1, max_length=64)
    profile: str | None = None
    storage_root_id: int | None = None
    storage_endpoint_id: int | None = None


def _replace_map_json(value: dict[str, str] | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


@router.get("/global", dependencies=[Depends(admin_or_internal)])
def get_global_naming_policy(db: Session = Depends(get_db)):
    return ui_data(load_global_policy(db))


@router.put("/global")
def put_global_naming_policy(payload: GlobalNamingPolicyPayload, db: Session = Depends(get_db), request: Request = None):
    actor = _require_admin(request)
    try:
        validate_template_tokens(payload.template)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.execute(
        text(
            """
            INSERT INTO naming_policy_global (
                id, group_prefix, template, normalize_uppercase, max_sam_length, replace_map_json, rootcode_strategy
            )
            VALUES (
                1, :group_prefix, :template, :normalize_uppercase, :max_sam_length, :replace_map_json, :rootcode_strategy
            )
            ON DUPLICATE KEY UPDATE
                group_prefix = VALUES(group_prefix),
                template = VALUES(template),
                normalize_uppercase = VALUES(normalize_uppercase),
                max_sam_length = VALUES(max_sam_length),
                replace_map_json = VALUES(replace_map_json),
                rootcode_strategy = VALUES(rootcode_strategy),
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "group_prefix": payload.group_prefix,
            "template": payload.template,
            "normalize_uppercase": 1 if payload.normalize_uppercase else 0,
            "max_sam_length": int(payload.max_sam_length),
            "replace_map_json": _replace_map_json(payload.replace_map_json),
            "rootcode_strategy": serialize_rootcode_strategy_for_storage(payload.rootcode_strategy),
        },
    )
    db.commit()
    _audit(actor, "naming_policy.global_updated", target_display="global", context={"template": payload.template, "group_prefix": payload.group_prefix})
    return ui_data(load_global_policy(db))


@router.get("/zones/{zone_id}", dependencies=[Depends(admin_or_internal)])
def get_zone_naming_policy(zone_id: int, db: Session = Depends(get_db)):
    if not _zone_exists(db, zone_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    row = load_zone_policy(db, zone_id)
    if row is not None:
        return ui_data(row, meta={"zone_id": int(zone_id)})

    return ui_data(
        {
            "zone_id": int(zone_id),
            "override_enabled": False,
            "group_prefix": None,
            "template": None,
            "normalize_uppercase": None,
            "max_sam_length": None,
            "replace_map_json": None,
            "rootcode_strategy": None,
        },
        meta={"zone_id": int(zone_id)},
    )


@router.put("/zones/{zone_id}")
def put_zone_naming_policy(
    zone_id: int,
    payload: ZoneNamingPolicyPayload,
    db: Session = Depends(get_db),
    request: Request = None,
):
    actor = _require_admin(request)
    if not _zone_exists(db, zone_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    if payload.template is not None:
        try:
            validate_template_tokens(payload.template)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.execute(
        text(
            """
            INSERT INTO naming_policy_overrides (
                scope_type, scope_id, override_enabled, group_prefix, template, normalize_uppercase, max_sam_length, replace_map_json, rootcode_strategy
            )
            VALUES (
                'zone', :zone_id, :override_enabled, :group_prefix, :template, :normalize_uppercase, :max_sam_length, :replace_map_json, :rootcode_strategy
            )
            ON DUPLICATE KEY UPDATE
                override_enabled = VALUES(override_enabled),
                group_prefix = VALUES(group_prefix),
                template = VALUES(template),
                normalize_uppercase = VALUES(normalize_uppercase),
                max_sam_length = VALUES(max_sam_length),
                replace_map_json = VALUES(replace_map_json),
                rootcode_strategy = VALUES(rootcode_strategy),
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "zone_id": int(zone_id),
            "override_enabled": 1 if payload.override_enabled else 0,
            "group_prefix": payload.group_prefix,
            "template": payload.template,
            "normalize_uppercase": None
            if payload.normalize_uppercase is None
            else (1 if payload.normalize_uppercase else 0),
            "max_sam_length": payload.max_sam_length,
            "replace_map_json": _replace_map_json(payload.replace_map_json),
            "rootcode_strategy": (
                serialize_rootcode_strategy_for_storage(payload.rootcode_strategy)
                if payload.rootcode_strategy is not None
                else None
            ),
        },
    )
    db.commit()
    _audit(actor, "naming_policy.zone_updated", target_id=int(zone_id), target_display=f"zone {zone_id}", context={"override_enabled": payload.override_enabled, "template": payload.template})
    return ui_data(load_zone_policy(db, zone_id), meta={"zone_id": int(zone_id)})


class NamingRootsPreviewPayload(BaseModel):
    zone_id: int | None = None
    storage_endpoint_id: int | None = None
    # Template being edited, not saved yet (applied at the level of the scope)
    template: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=3, ge=1, le=10)


@router.post("/preview-roots", dependencies=[Depends(admin_or_internal)])
def preview_root_groups(payload: NamingRootsPreviewPayload, db: Session = Depends(get_db)):
    """READ / WRITE group names of a few real storage roots of a file server or a zone.

    Same rule as the approvals (resolve_storage_root_group_name), with the template being edited when given.
    """
    if payload.storage_endpoint_id:
        scope, where, params = "storage_endpoint", "sr.storage_endpoint_id = :id", {"id": int(payload.storage_endpoint_id)}
    elif payload.zone_id:
        scope, where, params = "zone", "se.zone_id = :id", {"id": int(payload.zone_id)}
    else:
        raise HTTPException(status_code=422, detail="zone_id or storage_endpoint_id is required")
    rows = db.execute(
        text(
            f"""
            SELECT sr.id, sr.name, sr.root_path
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            WHERE {where}
            ORDER BY sr.name
            LIMIT :limit
            """
        ),
        {**params, "limit": int(payload.limit)},
    ).mappings().all()
    items = []
    try:
        for row in rows:
            naming = resolve_storage_root_naming(db, int(row["id"]), draft_scope=scope, draft_template=payload.template)
            if naming is None:
                continue
            effective, zone_code, root_path = naming
            names = {
                level: resolve_group_name_from_effective_policy(
                    effective_policy=effective, zone_code=zone_code, storage_root_path=root_path, perm=level
                )["samAccountName"]
                for level in ("READ", "WRITE")
            }
            items.append({"storage_root_id": int(row["id"]), "name": row["name"], "root_path": row["root_path"],
                          "read_group": names["READ"], "write_group": names["WRITE"]})
    except ValueError as exc:  # unknown token in the template being edited
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Groups already in the directory keep their name and OU when the rule changes
    existing = db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM storage_root_access_profiles p
            JOIN storage_roots sr ON sr.id = p.storage_root_id
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            WHERE {where} AND UPPER(COALESCE(p.status, '')) IN ('SUCCEEDED', 'ADOPTING')
            """
        ),
        params,
    ).scalar()
    return ui_data({"items": items, "existing_groups": int(existing or 0)})


@router.post("/preview", dependencies=[Depends(admin_or_internal)])
def preview_group_name(payload: NamingPreviewPayload, db: Session = Depends(get_db)):
    try:
        storage_root_naming = (
            resolve_storage_root_naming(db, int(payload.storage_root_id)) if payload.storage_root_id else None
        )
        if storage_root_naming is not None:
            # Same rule as the groups actually created for this storage root
            effective_policy, zone_code, _root_path = storage_root_naming
        else:
            zone_id, zone_code = resolve_zone_context(db, payload.zone_id)
            effective_policy = resolve_effective_policy(db, zone_id)
            endpoint_id = int(payload.storage_endpoint_id or 0) or None
            if endpoint_id is not None:
                row = db.execute(
                    text("SELECT naming_template FROM storage_endpoints WHERE id = :endpoint_id LIMIT 1"),
                    {"endpoint_id": int(endpoint_id)},
                ).mappings().first()
                endpoint_template = str((row or {}).get("naming_template") or "").strip() or None
                if endpoint_template:
                    effective_policy = {**effective_policy, "template": endpoint_template}

        group = resolve_group_name_from_effective_policy(
            effective_policy=effective_policy,
            zone_code=zone_code,
            storage_root_path=payload.storage_root_path,
            perm=payload.perm,
            profile=payload.profile,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ui_data(group)
