from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.routers._helpers import ui_data
from app.services.naming_policy import (
    load_global_policy,
    load_zone_policy,
    resolve_effective_policy,
    resolve_group_name_from_effective_policy,
    resolve_zone_context,
    serialize_rootcode_strategy_for_storage,
    validate_template_tokens,
)

router = APIRouter(prefix="/naming-policies", tags=["naming_policies"])


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


@router.get("/global")
def get_global_naming_policy(db: Session = Depends(get_db)):
    return ui_data(load_global_policy(db))


@router.put("/global")
def put_global_naming_policy(payload: GlobalNamingPolicyPayload, db: Session = Depends(get_db)):
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
    return ui_data(load_global_policy(db))


@router.get("/zones/{zone_id}")
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
):
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
    return ui_data(load_zone_policy(db, zone_id), meta={"zone_id": int(zone_id)})


@router.post("/preview")
def preview_group_name(payload: NamingPreviewPayload, db: Session = Depends(get_db)):
    try:
        zone_id, zone_code = resolve_zone_context(db, payload.zone_id)
        effective_policy = resolve_effective_policy(db, zone_id)

        endpoint_template: str | None = None
        endpoint_id = int(payload.storage_endpoint_id or 0) or None
        storage_root_id = int(payload.storage_root_id or 0) or None

        if endpoint_id is not None:
            row = db.execute(
                text(
                    """
                    SELECT naming_template
                    FROM storage_endpoints
                    WHERE id = :endpoint_id
                    LIMIT 1
                    """
                ),
                {"endpoint_id": int(endpoint_id)},
            ).mappings().first()
            endpoint_template = str((row or {}).get("naming_template") or "").strip() or None
        elif storage_root_id is not None:
            row = db.execute(
                text(
                    """
                    SELECT se.naming_template
                    FROM storage_roots sr
                    JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                    WHERE sr.id = :storage_root_id
                    LIMIT 1
                    """
                ),
                {"storage_root_id": int(storage_root_id)},
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
